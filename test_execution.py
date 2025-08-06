#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
测试脚本：验证打包后的Python代码执行功能
"""

import os
import sys

# 添加测试函数
def test_python_execution():
    """测试Python代码执行功能"""
    # 导入agent core模块
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    
    try:
        # 处理文件名中的空格
        import importlib.util
        spec = importlib.util.spec_from_file_location("agent_core", "agent core.py")
        agent_core = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(agent_core)
        
        execute_python_code_direct = agent_core.execute_python_code_direct
        execute_python_code = agent_core.execute_python_code
        
        print("🧪 测试Python代码执行功能")
        print("=" * 50)
        
        # 测试1：基本Python代码
        print("\n📋 测试1：基本Python代码执行")
        test_code1 = """
import os
import json
print("测试基本Python功能:")
print(f"当前工作目录: {os.getcwd()}")
print(f"Python版本: {sys.version}")

# 测试数据处理
data = {"test": "success", "number": 42}
print(f"JSON数据: {json.dumps(data, ensure_ascii=False)}")
"""
        result1 = execute_python_code_direct(test_code1)
        print(result1)
        
        # 测试2：创建文件并执行
        print("\n📋 测试2：文件创建和执行")
        test_script_content = '''
import os
print("这是从文件执行的Python代码")
print(f"文件执行时的工作目录: {os.getcwd()}")

# 创建一个简单的数据文件
test_data = {
    "message": "文件执行测试成功",
    "files": os.listdir(".")[:5]  # 列出前5个文件
}

import json
with open("test_output.json", "w", encoding="utf-8") as f:
    json.dump(test_data, f, ensure_ascii=False, indent=2)

print("✅ 已创建测试输出文件: test_output.json")
'''
        
        # 创建测试脚本文件
        with open("test_script.py", "w", encoding="utf-8") as f:
            f.write(test_script_content)
        
        result2 = execute_python_code("test_script.py")
        print(result2)
        
        # 验证输出文件
        if os.path.exists("test_output.json"):
            with open("test_output.json", "r", encoding="utf-8") as f:
                output_data = json.load(f)
            print(f"✅ 验证输出文件内容: {output_data}")
        
        # 清理测试文件
        for test_file in ["test_script.py", "test_output.json"]:
            if os.path.exists(test_file):
                os.remove(test_file)
                print(f"🧹 已清理测试文件: {test_file}")
        
        print("\n✅ 所有测试完成！")
        
    except ImportError as e:
        print(f"❌ 导入错误: {e}")
        print("请确保agent_core.py在当前目录")
    except Exception as e:
        print(f"❌ 测试失败: {e}")

if __name__ == "__main__":
    test_python_execution()