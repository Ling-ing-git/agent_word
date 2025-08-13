# -*- coding: utf-8 -*-
# 批量生成并合并：
# - 输入：模板文件、JSON（数组，每个元素是与 word_replace.replace_docx 相同格式的映射对象）
# - 对每个映射生成一个单独副本（调用 replace_docx）
# - 最终将所有副本按顺序合并为一个 .docx，组与组之间插入分页符
# - 合并依赖 docxcompose 以正确处理编号、样式与媒体资源
#
# 用法：
#   pip install lxml Pillow python-docx docxcompose
#   python word_batch.py template.docx data.json -o out.docx

import sys
import os
import json
import tempfile
import shutil
from typing import List, Dict, Any

from word_replace import replace_docx


def _ensure_packages():
    try:
        import docx  # noqa: F401
        from docxcompose.composer import Composer  # noqa: F401
    except Exception as e:
        raise RuntimeError("需要依赖 python-docx 与 docxcompose，请先安装：pip install python-docx docxcompose") from e


def _merge_docs_with_page_breaks(paths: List[str], out_path: str) -> None:
    from docx import Document
    from docxcompose.composer import Composer

    if not paths:
        raise ValueError("没有可合并的文档")

    master = Document(paths[0])
    composer = Composer(master)

    for p in paths[1:]:
        master.add_page_break()
        composer.append(Document(p))

    composer.save(out_path)


def batch_replace_and_merge(template_path: str, mappings: List[Dict[str, Any]], out_path: str) -> Dict[str, Any]:
    if not os.path.exists(template_path):
        raise FileNotFoundError(f"模板文件不存在：{template_path}")
    if not isinstance(mappings, list) or not all(isinstance(m, dict) for m in mappings):
        raise ValueError("mappings 需为对象数组，例如 [{...}, {...}]")

    _ensure_packages()

    tmp_dir = tempfile.mkdtemp(prefix="word_batch_")
    generated_paths: List[str] = []
    reports: List[Dict[str, Any]] = []

    try:
        # 逐组生成
        for idx, mapping in enumerate(mappings, start=1):
            out_i = os.path.join(tmp_dir, f"doc_{idx}.docx")
            report = replace_docx(template_path, mapping, out_i)
            generated_paths.append(out_i)
            reports.append({"index": idx, **report})

        # 合并
        _merge_docs_with_page_breaks(generated_paths, out_path)

        return {
            "ok": True,
            "count": len(generated_paths),
            "output": out_path,
            "tmpDir": tmp_dir,
            "groups": reports,
        }
    except Exception as e:
        return {
            "ok": False,
            "error": str(e),
        }
    finally:
        # 清理临时目录
        try:
            shutil.rmtree(tmp_dir)
        except Exception:
            pass


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="批量生成并合并 DOCX（分页符隔开）")
    parser.add_argument("template", help="模板 .docx 路径")
    parser.add_argument("json_list", help="JSON 文件路径（数组，每个元素为映射对象）")
    parser.add_argument("-o", "--output", required=True, help="合并输出 .docx 路径")

    args = parser.parse_args()

    try:
        with open(args.json_list, "r", encoding="utf-8") as f:
            data = json.load(f)
        report = batch_replace_and_merge(args.template, data, args.output)
        sys.stdout.write(json.dumps(report, ensure_ascii=False, indent=2))
    except Exception as e:
        sys.stderr.write(f"Error: {e}\n")
        sys.exit(1)