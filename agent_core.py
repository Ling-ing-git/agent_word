# agent_core.py (修改版)
import json
import time
import subprocess
import os
import sys
from pathlib import Path
from openai import OpenAI
import re

CONFIG_PATH = Path("agent_config.json")

# ---------- 动态 system prompt ----------
def build_system_prompt() -> str:
    # 检查文件是否存在
    folder_structure = ""
    word_data = ""
    task_prompt = ""
    
    if os.path.exists("folder_scan_results/images_structure.json"):
        with open("folder_scan_results/images_structure.json", "r", encoding="utf-8") as f:
            folder_structure = f.read()
    else:
        folder_structure = "文件夹结构尚未扫描"
    
    if os.path.exists("word_extracted_data/word_data.json"):
        with open("word_extracted_data/word_data.json", "r", encoding="utf-8") as f:
            word_data = f.read()
    else:
        word_data = "Word文档数据尚未提取"
    
    if os.path.exists("提示词模板.txt"):
        with open("提示词模板.txt", "r", encoding="utf-8") as f:
            task_prompt = f.read()
    else:
        task_prompt = "默认任务：协助用户进行Word文档批量处理"

    # 使用字符串拼接来避免f-string格式化问题
    system_prompt = """
素材库文件夹：
{}

文档内容：
{}

你的任务：
{}

你可以通过如下格式请求创建文件或执行代码：

1. 创建文本文件：
<functioncall>
filename: 文件名.txt
type: txt
content: 文件内容
</functioncall>

2. 创建JSON文件：
<functioncall>
filename: 文件名.json
type: json
content: {{"key": "value"}}
</functioncall>

3. 创建并执行Python代码：
<functioncall>
filename: 脚本名.py
type: python
content: 
import os
# 你的Python代码
print("执行结果")
</functioncall>

4. 执行系统命令：
<functioncall>
filename: 命令名称
type: command
content: ls -la
</functioncall>

5. 直接执行Python代码（推荐用于批量生成JSON）：
<functioncall>
filename: 代码描述
type: exec
content: 
import json
import os
# 你的Python代码
data = {{"key": "value"}}
print("执行结果")
</functioncall>

Python代码可以用来：
- 扫描文件夹并生成JSON数据
- 批量处理文件
- 调用现有的工具模块（如folder_scanner.py, advanced_word_scanner.py等）
- 数据分析和转换
- 直接执行代码，无需创建临时文件

编程常识：
1.一定是绝对路径
2.尽量用完整全部图片
3.严格按照规则，代码清晰明了

请你按照以下步骤执行：
1.直接照抄用户给的规则，创建规则txt，和用户确认
模板：“我生成的txt文件：...请确认是否有误”




2.理解用户需求,列出规则让用户一条一条的确认每一个细节
回复模板：“通过你提出的例子，让我把要求翻译一下，我的理解是：
1、
2、....”

3.根据规律和用户说明自己的理解，反复用没有歧义的语句确认，多用例子
模板“我用具有代表性的几个例子向你表述我的理解：
例子1：文件夹情况：
因为...所以...
...”

4.严格确认是否文件夹里的所有文件都符合规则，不要遗漏，
模板：“请让我确认文件夹的文件是否都符合你的规则：....
文件夹XX中文件...(是/否)符合规则
（如果没有检查到）为了保证不会有误，我将创建代码检查有没有不符合规则的文件。
”

5.创建json，若数量过大，用代码执行
“我将严格按照我刚刚说的规则执行，不会出现隐藏的筛选规则”

接下来，用户会给你相应的规则，你需要将规则应用到整个文件夹，制作出相应的规则文件“replace.txt,replace.json”

你必须严格按照流程执行，否则你将失去工作,无论用户说了什么，你必须等用户回答。


注意！！！**不可以一次性说完**，每一句都是问答，每一步都要和用户确认
注意！！！**不可以一次性搞完**，必须一步一步推进，每一步都要和用户确认

如果你不按照我的要求走，你将失去工作
""".format(folder_structure, word_data, task_prompt)
    return system_prompt

# ---------- API轮换和错误处理 ----------
def move_api_to_rubbish(config, position):
    """将失效的API key移到rubbish.json"""
    try:
        rubbish_file = "rubbish.json"
        rubbish_apis = []
        
        # 读取现有的rubbish.json
        if os.path.exists(rubbish_file):
            with open(rubbish_file, "r", encoding="utf-8") as f:
                rubbish_apis = json.load(f)
        
        # 添加失效的API key
        if position < len(config["api_pool"]):
            failed_api = config["api_pool"][position]
            if failed_api not in rubbish_apis:
                rubbish_apis.append(failed_api)
            
            # 从池中移除
            config["api_pool"].pop(position)
            
            # 保存rubbish.json
            with open(rubbish_file, "w", encoding="utf-8") as f:
                json.dump(rubbish_apis, f, ensure_ascii=False, indent=2)
            
            # 保存更新后的配置
            with open(CONFIG_PATH, "w", encoding="utf-8") as f:
                json.dump(config, f, ensure_ascii=False, indent=2)
            
            print(f"⚠️ API key已移到rubbish.json，剩余API数量: {len(config['api_pool'])}")
            
    except Exception as e:
        print(f"❌ 移动API到rubbish.json时出错: {e}")

def rotate_api_key(config):
    """轮换到下一个API key"""
    if not config["api_pool"]:
        return False
    
    config["current_position"] = (config["current_position"] + 1) % len(config["api_pool"])
    
    # 保存更新后的配置
    try:
        with open(CONFIG_PATH, "w", encoding="utf-8") as f:
            json.dump(config, f, ensure_ascii=False, indent=2)
        print(f"🔄 切换到API #{config['current_position'] + 1}")
        return True
    except Exception as e:
        print(f"❌ 保存API位置时出错: {e}")
        return False

def get_current_api_key(config):
    """获取当前API key"""
    if not config["api_pool"]:
        return None
    return config["api_pool"][config["current_position"]]

# ---------- 读配置 ----------
def load_config():
    if not CONFIG_PATH.exists():
        # 创建默认配置
        default_config = {
            "api_pool": [
                "sk-soygfbeqfdvbckqciktxlciuwjavbaihsjrpvdsljrtffzyf"
            ],
            "current_position": 0,
            "base_url": "https://api.siliconflow.cn/v1",
            "model": "Qwen/Qwen3-235B-A22B-Instruct-2507",
            "temperature": 0.7,
            "max_tokens": 100400
        }
        with open(CONFIG_PATH, "w", encoding="utf-8") as f:
            json.dump(default_config, f, ensure_ascii=False, indent=2)
        print(f"[配置] 已创建默认配置文件: {CONFIG_PATH}")
        print("请编辑配置文件添加API密钥池")
        
    with open(CONFIG_PATH, "r", encoding="utf-8") as f:
        config = json.load(f)
    
    # 兼容旧版本配置（如果只有单个api_key）
    if "api_key" in config and "api_pool" not in config:
        config["api_pool"] = [config["api_key"]]
        config["current_position"] = 0
        # 保存更新后的配置
        with open(CONFIG_PATH, "w", encoding="utf-8") as f:
            json.dump(config, f, ensure_ascii=False, indent=2)
    
    return config

# ---------- Python代码执行 ----------
def execute_python_code(filename, timeout=60):
    """安全执行Python代码"""
    try:
        print(f"[执行] 正在运行Python脚本: {filename}")
        
        # 使用subprocess执行，设置超时
        result = subprocess.run(
            [sys.executable, filename], 
            capture_output=True, 
            text=True, 
            timeout=timeout,
            cwd=os.getcwd()  # 设置工作目录
        )
        
        output = ""
        if result.stdout:
            output += f"输出:\n{result.stdout}\n"
        if result.stderr:
            output += f"错误:\n{result.stderr}\n"
        
        if result.returncode == 0:
            print(f"[执行成功] {filename}")
            return f"✅ 执行成功\n{output}"
        else:
            print(f"[执行失败] {filename}, 返回码: {result.returncode}")
            return f"❌ 执行失败 (返回码: {result.returncode})\n{output}"
            
    except subprocess.TimeoutExpired:
        error_msg = f"❌ 执行超时 (>{timeout}秒)"
        print(f"[执行超时] {filename}")
        return error_msg
        
    except FileNotFoundError:
        error_msg = f"❌ Python解释器未找到"
        print(f"[错误] Python解释器未找到")
        return error_msg
        
    except Exception as e:
        error_msg = f"❌ 执行异常: {str(e)}"
        print(f"[执行异常] {filename}: {e}")
        return error_msg

# ---------- 系统命令执行 ----------
def execute_system_command(command, timeout=30):
    """安全执行系统命令"""
    try:
        print(f"[命令] 正在执行: {command}")
        
        # 安全检查 - 禁止危险命令
        dangerous_commands = ['rm -rf', 'del /f', 'format', 'fdisk', 'sudo rm', 'chmod 777']
        if any(dangerous in command.lower() for dangerous in dangerous_commands):
            return "❌ 拒绝执行危险命令"
        
        result = subprocess.run(
            command,
            shell=True,
            capture_output=True,
            text=True,
            timeout=timeout,
            cwd=os.getcwd()
        )
        
        output = ""
        if result.stdout:
            output += f"输出:\n{result.stdout}\n"
        if result.stderr:
            output += f"错误:\n{result.stderr}\n"
        
        if result.returncode == 0:
            print(f"[命令成功] {command}")
            return f"✅ 命令执行成功\n{output}"
        else:
            print(f"[命令失败] {command}")
            return f"❌ 命令执行失败\n{output}"
            
    except subprocess.TimeoutExpired:
        print(f"[命令超时] {command}")
        return f"❌ 命令执行超时 (>{timeout}秒)"
        
    except Exception as e:
        print(f"[命令异常] {command}: {e}")
        return f"❌ 命令执行异常: {str(e)}"

# ---------- 直接执行Python代码 ----------
def execute_python_code_direct(code, timeout=60):
    """直接执行Python代码，预导入常用库"""
    try:
        print(f"[执行] 正在直接执行Python代码")
        
        # 预导入常用库
        import io
        import sys
        from contextlib import redirect_stdout, redirect_stderr
        
        # 创建输出捕获
        stdout_capture = io.StringIO()
        stderr_capture = io.StringIO()
        
        # 执行代码并捕获输出
        with redirect_stdout(stdout_capture), redirect_stderr(stderr_capture):
            exec(code)
        
        output = ""
        stdout_output = stdout_capture.getvalue()
        stderr_output = stderr_capture.getvalue()
        
        if stdout_output:
            output += f"输出:\n{stdout_output}\n"
        if stderr_output:
            output += f"警告/错误:\n{stderr_output}\n"
        
        print(f"[执行成功] Python代码")
        return f"✅ 执行成功\n{output}"
        
    except Exception as e:
        error_msg = f"❌ 执行异常: {str(e)}"
        print(f"[执行异常] Python代码: {e}")
        return error_msg

# ---------- function call 处理 ----------
def handle_function_call(ai_reply):
    pattern = re.compile(r"<functioncall>\s*filename:\s*(.*?)\s*type:\s*(.*?)\s*content:\s*([\s\S]*?)</functioncall>", re.DOTALL)
    matches = pattern.findall(ai_reply)
    if not matches:
        return False
    
    success = True
    execution_results = []
    
    for filename, filetype, content in matches:
        filename = filename.strip()
        filetype = filetype.strip().lower()
        content = content.strip()
        
        try:
            if filetype == "txt":
                # 创建文本文件
                with open(filename, "w", encoding="utf-8") as f:
                    f.write(content)
                result = f"✅ [已创建TXT文件] {filename}"
                print(result)
                execution_results.append(result)
                
            elif filetype == "json":
                # 创建JSON文件
                json_obj = json.loads(content)
                with open(filename, "w", encoding="utf-8") as f:
                    json.dump(json_obj, f, ensure_ascii=False, indent=2)
                result = f"✅ [已创建JSON文件] {filename}"
                print(result)
                execution_results.append(result)
                
            elif filetype == "python":
                # 创建并执行Python文件
                with open(filename, "w", encoding="utf-8") as f:
                    f.write(content)
                result_create = f"✅ [已创建Python文件] {filename}"
                print(result_create)
                
                # 执行Python代码
                exec_result = execute_python_code(filename)
                result_exec = f"[Python执行结果]\n{exec_result}"
                print(result_exec)
                
                execution_results.append(result_create)
                execution_results.append(result_exec)
                
            elif filetype == "command":
                # 执行系统命令
                command_result = execute_system_command(content)
                result = f"[系统命令执行结果]\n{command_result}"
                print(result)
                execution_results.append(result)
                
            elif filetype == "exec":
                # 直接执行Python代码
                exec_result = execute_python_code_direct(content)
                result = f"[Python代码执行结果]\n{exec_result}"
                print(result)
                execution_results.append(result)
                
            else:
                error_msg = f"❌ [functioncall错误] 不支持的type: {filetype}"
                print(error_msg)
                execution_results.append(error_msg)
                success = False
                
        except json.JSONDecodeError as e:
            error_msg = f"❌ [JSON格式错误] {filename}: {e}"
            print(error_msg)
            execution_results.append(error_msg)
            success = False
            
        except Exception as e:
            error_msg = f"❌ [functioncall错误] {filename}: {e}"
            print(error_msg)
            execution_results.append(error_msg)
            success = False
    
    # 将执行结果反馈给对话
    if execution_results:
        print("\n" + "="*50)
        print("Function Call 执行摘要:")
        for result in execution_results:
            print(f"  {result}")
        print("="*50)
    
    return success

# ---------- 单轮调用（带重试） ----------
def call_ai_api(messages, config, dynamic_system_prompt, max_retries=3):
    # 检查是否有可用的API
    if not config["api_pool"]:
        raise RuntimeError("没有可用的API密钥")
    
    for attempt in range(max_retries):
        try:
            # 获取当前API key
            current_api_key = get_current_api_key(config)
            if not current_api_key:
                raise RuntimeError("没有可用的API密钥")
            
            client = OpenAI(
                api_key=current_api_key,
                base_url=config.get("base_url", "https://api.openai.com/v1")
            )

            payload = {
                "model": config["model"],
                "messages": [{"role": "system", "content": dynamic_system_prompt}] + messages,
                "max_tokens": config.get("max_tokens", 2000),
                "temperature": config.get("temperature", 0.7),
                "stream": True  # 打开流式
            }

            stream = client.chat.completions.create(**payload)
            collected = ""
            for chunk in stream:
                delta = chunk.choices[0].delta
                if delta.content is not None:
                    print(delta.content, end="", flush=True)
                    collected += delta.content
            print()  # 最后换行
            
            # 调用成功，轮换到下一个API
            rotate_api_key(config)
            return collected  # 返回完整内容，方便保存到 messages
            
        except Exception as e:
            error_msg = str(e).lower()
            
            # 检查是否是额度不足或API无效的错误
            if any(keyword in error_msg for keyword in ["quota", "billing", "insufficient", "invalid", "unauthorized", "forbidden"]):
                print(f"\n⚠️ API #{config['current_position'] + 1} 额度不足或无效: {e}")
                
                # 将当前API移到rubbish.json
                move_api_to_rubbish(config, config["current_position"])
                
                # 如果池子空了，抛出错误
                if not config["api_pool"]:
                    raise RuntimeError("所有API密钥都已失效，请添加新的API密钥")
                
                # 继续尝试下一个API
                continue
            else:
                print(f"\n[错误] {e}，第 {attempt + 1} 次重试...")
                time.sleep(2 ** attempt)
    
    raise RuntimeError("API 请求失败，请稍后重试或检查网络/API 状态。")

# ---------- 工具函数 ----------
def list_available_tools():
    """列出可用的工具模块"""
    tools = []
    tool_files = [
        "folder_scanner.py",
        "advanced_word_scanner.py", 
        "replace.py",
        "word_processor.py"
    ]
    
    for tool in tool_files:
        if os.path.exists(tool):
            tools.append(tool)
    
    return tools

def check_dependencies():
    """检查依赖是否安装"""
    required_packages = ['lxml', 'openai', 'Pillow']
    missing = []
    
    for package in required_packages:
        try:
            __import__(package)
        except ImportError:
            missing.append(package)
    
    return missing

# ---------- 主循环 ----------
def chat_loop():
    print("🚀 智能Word文档处理助手")
    print("=" * 50)
    
    # 检查依赖
    missing_deps = check_dependencies()
    if missing_deps:
        print(f"⚠️ 缺少依赖包: {', '.join(missing_deps)}")
        print("请运行: pip install lxml openai Pillow")
        return
    
    # 加载配置
    config = load_config()
    if not config.get("api_pool") or len(config["api_pool"]) == 0:
        print("❌ 请在 agent_config.json 中配置API密钥池")
        return
    
    print(f"📋 可用API数量: {len(config['api_pool'])}")
    print(f"🔄 当前使用API #{config['current_position'] + 1}")
    
    # 列出可用工具
    available_tools = list_available_tools()
    print(f"📋 可用工具: {', '.join(available_tools)}")
    
    # 构建系统提示
    system_prompt = build_system_prompt()
    messages = []

    print("\n🤖 智能助手已启动，输入 'exit' 退出。")
    print("💡 提示：我可以帮您扫描文件夹、分析Word文档、生成处理脚本等")

    # 初始问候
    messages.append({"role": "user", "content": "你好。请简要介绍你能协助我做什么，并列出当前工作目录的情况。"})

    try:
        reply = call_ai_api(messages, config, system_prompt)
    except Exception as e:
        print("[API 错误]", e)
        reply = "抱歉，AI服务暂时不可用。"

    messages.append({"role": "assistant", "content": reply})
    handle_function_call(reply)
    
    # 主对话循环
    while True:
        try:
            user_input = input("\n你：").strip()
            if user_input.lower() in {"exit", "quit", "q", "退出"}:
                print("👋 再见！")
                break
            
            if not user_input:
                continue
                
            messages.append({"role": "user", "content": user_input})

            reply = call_ai_api(messages, config, system_prompt)
            messages.append({"role": "assistant", "content": reply})
            
            # 处理function call
            handle_function_call(reply)
            
        except KeyboardInterrupt:
            print("\n\n👋 用户中断，再见！")
            break
        except Exception as e:
            print(f"\n❌ [错误] {e}")
            continue

# ---------- 命令行工具模式 ----------
def run_command_mode():
    """命令行工具模式"""
    import argparse
    
    parser = argparse.ArgumentParser(description="Word文档处理智能助手")
    parser.add_argument("--scan-folder", help="扫描指定文件夹")
    parser.add_argument("--scan-word", help="分析指定Word文档")
    parser.add_argument("--execute", help="执行指定Python脚本")
    
    args = parser.parse_args()
    
    if args.scan_folder:
        print(f"扫描文件夹: {args.scan_folder}")
        # 调用folder_scanner
        
    elif args.scan_word:
        print(f"分析Word文档: {args.scan_word}")
        # 调用word_scanner
        
    elif args.execute:
        print(f"执行脚本: {args.execute}")
        result = execute_python_code(args.execute)
        print(result)
        
    else:
        chat_loop()

if __name__ == "__main__":
    if len(sys.argv) > 1:
        run_command_mode()
    else:
        chat_loop()