#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
replace_docx_text.py

目的：
- 通过“直接替换 DOCX 内部 XML”的方式，完成两类任务：
  1) 替换可见文字（old -> new）
  2) 扫描提取可见文字（输出为纯文本）

特点：
- 仅依赖 Python 标准库：zipfile + xml.etree.ElementTree
- 仅操作 WordprocessingML 的可见文字节点 w:t，不改样式/图片/关系等其它内容
- 避免“误改”：只解析与文字相关的部件（正文、页眉、页脚、批注、脚注、尾注）

局限：
- 不跨 w:t 节点替换：若一个词被拆成多个运行/节点（例如中间有加粗/超链接），本脚本不会命中这种“跨节点”的替换；如有需要可升级实现。
- 被标记为删除修订（w:del）里的 w:t 也会被替换；如果你想忽略修订，需要在遍历时跳过拥有 w:del 祖先的 w:t。
- Word 的字段（如页码/目录）是动态生成的，手动改“显示文本”在 Word 刷新字段时可能被覆盖。

用法：
- 替换：python replace_docx_text.py <input.docx> <output.docx> <old_text> <new_text>
- 扫描：python replace_docx_text.py scan <input.docx> [output.txt]
"""

from __future__ import annotations

import sys
import re
import zipfile
import xml.etree.ElementTree as ET
from typing import Tuple, List

# WordprocessingML 命名空间定义（w 前缀指向的 URI）。
# 这是 DOCX（.docx）内部用于正文等的 XML 命名空间。
W_NS = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
NS = {"w": W_NS}

# 注册常用命名空间前缀，避免写回 XML 时生成 ns0 之类的临时前缀。
ET.register_namespace("w", W_NS)
ET.register_namespace("xml", "http://www.w3.org/XML/1998/namespace")

# 始终可能包含“可见文字”的部件路径（在 DOCX 压缩包里）。
ALWAYS_TARGETS = {
    "word/document.xml",   # 正文
    "word/footnotes.xml",  # 脚注
    "word/endnotes.xml",   # 尾注
}

# 符合这些模式的部件也可能包含可见文字：页眉、页脚、批注。
PATTERNS = [
    re.compile(r"^word/header\d*\.xml$"),    # 页眉（header.xml、header1.xml、...）
    re.compile(r"^word/footer\d*\.xml$"),    # 页脚
    re.compile(r"^word/comments\d*\.xml$"),  # 批注
]


def is_text_part(name: str) -> bool:
    """判断一个 ZIP 条目是否为“需要处理的文字部件”。

    仅处理：正文、页眉、页脚、批注、脚注、尾注。
    其它如样式（styles.xml）、关系（*.rels）、主题、媒体等与可见正文文字无关，跳过。
    """
    if name in ALWAYS_TARGETS:
        return True
    return any(p.match(name) for p in PATTERNS)


def replace_in_xml_bytes(xml_bytes: bytes, old: str, new: str) -> Tuple[bytes, int]:
    """在“单个 XML 文本”中，替换所有 w:t 节点的文本 old -> new。

    注意：不跨节点，仅对各自节点内的字符串做替换；
         例如 w:t("ABC") 不会与下一个节点 w:t("DEF") 拼接在一起匹配。

    返回：
      - 新 XML 的字节串（若没有任何变更，则直接返回原字节）
      - 本 XML 内发生的替换次数（命中数累加）
    """
    # 解析 XML。如果遇到损坏的 XML，调用者会捕获异常并原样拷贝。
    root = ET.fromstring(xml_bytes)

    total_replacements = 0

    # 遍历所有可见文字节点 w:t。
    # 提示：w:t 可能携带 xml:space="preserve" 来保留前后空格，
    # 我们仅修改 t.text，不动属性即可自然保留空格行为。
    for t in root.findall(".//w:t", NS):
        if t.text:
            count_here = t.text.count(old)
            if count_here:
                t.text = t.text.replace(old, new)
                total_replacements += count_here

    if total_replacements == 0:
        # 没有改变内容，直接返回原字节，避免无谓的重序列化差异。
        return xml_bytes, 0

    # 将修改后的 XML 写回字节串。
    # 使用 UTF-8 编码，并带上 XML 声明（<?xml version=...?>）。
    new_bytes = ET.tostring(root, encoding="utf-8", xml_declaration=True)
    return new_bytes, total_replacements


# —— 扫描相关 ——

# 新增：用图形界面对话框展示文本（若环境不支持图形界面则回退到控制台打印）
def show_text_dialog(title: str, text: str) -> None:
    """显示一个带滚动条的对话框展示文本；如果 GUI 不可用则打印到控制台。

    在 Linux/服务器无显示环境时，Tkinter 可能因为缺少 DISPLAY 而失败，
    我们捕获异常并回退到 print。
    """
    try:
        import tkinter as tk
        from tkinter import scrolledtext

        root = tk.Tk()
        root.title(title)
        # 合理默认尺寸，可调整
        root.geometry("800x600")

        # 文本区域（只读）
        st = scrolledtext.ScrolledText(root, wrap=tk.WORD)
        st.pack(fill=tk.BOTH, expand=True)
        st.insert(tk.END, text)
        st.configure(state="disabled")

        # 关闭按钮
        btn = tk.Button(root, text="OK", command=root.destroy)
        btn.pack(pady=8)

        root.mainloop()
    except Exception:
        # 无 GUI 环境或其他异常时，退回控制台输出
        print(text)


def extract_text_from_xml_bytes(xml_bytes: bytes) -> str:
    """从“单个 XML 文本”中提取可见文字：把所有 w:t 的文本直接拼接。

    说明：
    - 这是最直接、足够通用的做法，适合浏览核对内容。
    - 未尝试复原段落/换行（Word 内部的换行、段落边界可能体现在其它节点/属性中）。
    """
    root = ET.fromstring(xml_bytes)
    pieces: List[str] = []
    for t in root.findall(".//w:t", NS):
        pieces.append(t.text or "")
    return "".join(pieces)


def scan_docx_text(src_path: str) -> str:
    """扫描整个 DOCX，提取正文/页眉/页脚/批注/脚注/尾注中的可见文字。

    返回：
      - 拼接后的纯文本字符串；不同部件之间用一个空行分隔，便于阅读。
    """
    texts: List[str] = []
    with zipfile.ZipFile(src_path, "r") as zin:
        for item in zin.infolist():
            # 只处理 XML 且判断为“可能包含可见文字”的部件
            if item.filename.endswith(".xml") and is_text_part(item.filename):
                try:
                    xml_bytes = zin.read(item.filename)
                    texts.append(extract_text_from_xml_bytes(xml_bytes))
                except ET.ParseError:
                    # 单个部件解析失败：跳过，不影响整体扫描
                    pass
    # 用空行分隔不同来源部件的文字，避免混在一起难以阅读
    return "\n\n".join(filter(None, texts))


# —— 替换整个 DOCX ——

def replace_in_docx(src_path: str, dst_path: str, old: str, new: str) -> Tuple[int, int]:
    """在整个 DOCX（ZIP 包）中执行“可见文字替换”。

    流程：
    - 遍历压缩包内的所有条目；
    - 对“候选 XML 部件”（正文、页眉、页脚、批注、脚注、尾注）执行替换；
    - 其它文件原样拷贝；
    - 返回：(被修改的 XML 文件数, 替换命中的总次数)。
    """
    modified_files = 0
    total_replacements = 0

    # 以读取方式打开源 DOCX，同时以写入方式创建目标 DOCX。
    with zipfile.ZipFile(src_path, "r") as zin, zipfile.ZipFile(dst_path, "w", zipfile.ZIP_DEFLATED) as zout:
        for item in zin.infolist():
            data = zin.read(item.filename)

            # 仅对“候选 XML 部件”尝试解析与替换
            if item.filename.endswith(".xml") and is_text_part(item.filename):
                try:
                    data_new, count = replace_in_xml_bytes(data, old, new)
                except ET.ParseError:
                    # 若解析失败，为了稳妥起见，保持原样并视为无替换
                    data_new, count = data, 0

                if count > 0:
                    modified_files += 1
                    total_replacements += count
                    data = data_new

            # 写入目标 DOCX。这里直接把原 ZipInfo 用于写回，尽量保留时间戳等元信息。
            zout.writestr(item, data)

    return modified_files, total_replacements


def _print_usage() -> None:
    """打印命令行用法说明。"""
    print("Usage:")
    print("  Replace: python replace_docx_text.py <input.docx> <output.docx> <old_text> <new_text>")
    print("  Scan   : python replace_docx_text.py scan <input.docx> [output.txt]")
    print("  Scan GUI: python replace_docx_text.py scan <input.docx> --dialog")


def main() -> None:
    """命令行入口：根据参数执行“替换”或“扫描”。"""
    # 扫描模式：
    #   - 打印到屏幕：python replace_docx_text.py scan in.docx
    #   - 写入文件  ：python replace_docx_text.py scan in.docx out.txt
    #   - 弹出对话框：python replace_docx_text.py scan in.docx --dialog
    if len(sys.argv) >= 3 and sys.argv[1] == "scan":
        args = sys.argv[2:]
        if not args:
            _print_usage()
            sys.exit(1)
        src = args[0]
        dialog = False
        out_path = None
        # 解析可选参数
        if len(args) >= 2:
            if args[1] == "--dialog":
                dialog = True
            else:
                out_path = args[1]
        # 第三个参数若存在且是 --dialog，则同时支持输出文件 + 弹窗
        if len(args) >= 3 and args[2] == "--dialog":
            dialog = True

        text = scan_docx_text(src)
        if dialog:
            show_text_dialog("Scanned Text", text)
            return
        if out_path:
            with open(out_path, "w", encoding="utf-8") as f:
                f.write(text)
            print(f"Scanned text written to: {out_path}")
        else:
            print(text)
        return

    # 替换模式：python replace_docx_text.py in.docx out.docx old new
    if len(sys.argv) != 5:
        _print_usage()
        sys.exit(1)

    _, src, dst, old, new = sys.argv

    # 说明：若 new 含有特殊字符（& < > 等），写回 XML 时会自动按规范转义（&amp; &lt; &gt;），
    # 这是正确的行为。Word 打开时会按原字符显示，不需要手动解码。
    modified_files, total = replace_in_docx(src, dst, old, new)

    # 打印结果统计
    print(f"Done. Wrote: {dst}")
    print(f"Modified XML parts: {modified_files}")
    print(f"Total replacements: {total}")


if __name__ == "__main__":
    main()