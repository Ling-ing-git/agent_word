"""
OpenAI库配置示例
展示如何调用第三方模型、配置自定义URL、消息传递和参数设置
"""

import os
from openai import OpenAI

# 方法1: 使用环境变量配置
def setup_openai_with_env():
    """使用环境变量配置OpenAI客户端"""
    client = OpenAI(
        api_key=os.getenv("OPENAI_API_KEY"),
        base_url=os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1")  # 默认官方URL
    )
    return client

# 方法2: 直接配置第三方模型
def setup_custom_model():
    """配置第三方模型服务"""
    client = OpenAI(
        api_key="your-custom-api-key",
        base_url="https://your-custom-api.com/v1"  # 第三方API端点
    )
    return client

# 方法3: 配置本地部署的模型
def setup_local_model():
    """配置本地部署的模型"""
    client = OpenAI(
        api_key="local-key",  # 本地服务可能不需要真实密钥
        base_url="http://localhost:8000/v1"  # 本地服务地址
    )
    return client

# 基本对话调用
def basic_chat_example():
    """基本对话示例"""
    client = setup_openai_with_env()
    
    response = client.chat.completions.create(
        model="gpt-3.5-turbo",  # 或其他支持的模型
        messages=[
            {"role": "system", "content": "你是一个有帮助的AI助手。"},
            {"role": "user", "content": "请介绍一下Python编程语言。"}
        ],
        temperature=0.7,
        max_tokens=500,
        top_p=0.9
    )
    
    return response.choices[0].message.content

# 多轮对话示例
def multi_turn_conversation():
    """多轮对话示例"""
    client = setup_openai_with_env()
    
    # 构建对话历史
    conversation_history = [
        {"role": "system", "content": "你是一个编程导师。"},
        {"role": "user", "content": "我想学习Python"},
        {"role": "assistant", "content": "很好！Python是一门优秀的编程语言。你想从哪个方面开始学习？"},
        {"role": "user", "content": "请教我变量的概念"}
    ]
    
    response = client.chat.completions.create(
        model="gpt-3.5-turbo",
        messages=conversation_history,
        temperature=0.5,
        max_tokens=300
    )
    
    return response.choices[0].message.content

# 流式输出示例
def streaming_chat_example():
    """流式输出示例"""
    client = setup_openai_with_env()
    
    stream = client.chat.completions.create(
        model="gpt-3.5-turbo",
        messages=[
            {"role": "user", "content": "请写一个关于春天的短诗"}
        ],
        stream=True,
        temperature=0.8
    )
    
    full_response = ""
    for chunk in stream:
        if chunk.choices[0].delta.content is not None:
            content = chunk.choices[0].delta.content
            print(content, end='', flush=True)
            full_response += content
    
    return full_response

# 参数配置详解
def advanced_parameter_config():
    """高级参数配置示例"""
    client = setup_openai_with_env()
    
    response = client.chat.completions.create(
        model="gpt-3.5-turbo",
        messages=[
            {"role": "system", "content": "你是一个创意写作助手。"},
            {"role": "user", "content": "写一个科幻故事的开头"}
        ],
        
        # 创造性参数
        temperature=0.9,        # 高创造性
        top_p=0.95,            # 核采样
        
        # 长度控制
        max_tokens=800,        # 最大输出长度
        
        # 重复控制
        frequency_penalty=0.3,  # 降低重复词汇
        presence_penalty=0.2,   # 鼓励新话题
        
        # 其他参数
        n=1,                   # 生成1个回复
        stop=None,             # 停止词
        user="user_123"        # 用户标识
    )
    
    return response

# 错误处理示例
def robust_api_call():
    """带错误处理的API调用"""
    client = setup_openai_with_env()
    
    try:
        response = client.chat.completions.create(
            model="gpt-3.5-turbo",
            messages=[
                {"role": "user", "content": "Hello, world!"}
            ],
            timeout=30  # 设置超时时间
        )
        
        return {
            "success": True,
            "content": response.choices[0].message.content,
            "usage": response.usage.dict() if response.usage else None
        }
        
    except Exception as e:
        return {
            "success": False,
            "error": str(e),
            "error_type": type(e).__name__
        }

# 配置文件示例
OPENAI_CONFIGS = {
    "official": {
        "base_url": "https://api.openai.com/v1",
        "models": ["gpt-3.5-turbo", "gpt-4", "gpt-4-turbo"]
    },
    "azure": {
        "base_url": "https://your-resource.openai.azure.com/",
        "models": ["gpt-35-turbo", "gpt-4"]
    },
    "custom": {
        "base_url": "https://your-custom-api.com/v1",
        "models": ["custom-model-1", "custom-model-2"]
    },
    "local": {
        "base_url": "http://localhost:8000/v1",
        "models": ["local-llama", "local-chatglm"]
    }
}

def create_client_by_config(config_name: str):
    """根据配置创建客户端"""
    config = OPENAI_CONFIGS.get(config_name)
    if not config:
        raise ValueError(f"未知配置: {config_name}")
    
    return OpenAI(
        api_key=os.getenv(f"{config_name.upper()}_API_KEY"),
        base_url=config["base_url"]
    )

# 使用示例
if __name__ == "__main__":
    # 设置环境变量示例
    os.environ["OPENAI_API_KEY"] = "your-api-key"
    os.environ["OPENAI_BASE_URL"] = "https://api.openai.com/v1"
    
    # 测试基本对话
    print("=== 基本对话测试 ===")
    try:
        result = basic_chat_example()
        print(f"回复: {result}")
    except Exception as e:
        print(f"错误: {e}")
    
    # 测试多轮对话
    print("\n=== 多轮对话测试 ===")
    try:
        result = multi_turn_conversation()
        print(f"回复: {result}")
    except Exception as e:
        print(f"错误: {e}")
    
    # 测试流式输出
    print("\n=== 流式输出测试 ===")
    try:
        print("流式回复: ", end="")
        streaming_chat_example()
        print()  # 换行
    except Exception as e:
        print(f"错误: {e}")