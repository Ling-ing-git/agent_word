#!/usr/bin/env python3
"""
OpenAI管理器使用示例
演示如何使用OpenAIManager进行模型调用、验证和随机调用
"""

from openai_manager import OpenAIManager


def main():
    # 初始化管理器
    manager = OpenAIManager("config.json")
    
    print("=== OpenAI管理器使用示例 ===\n")
    
    # 1. 显示配置信息
    print("1. 当前配置信息:")
    configs = manager.get_config_info()
    for config in configs:
        print(f"  配置 {config['index']}: {config['model']} @ {config['url']} (API Key: {config['apikey']})")
    print()
    
    # 2. 验证所有配置
    print("2. 验证所有配置:")
    validation_results = manager.validate_all_configs()
    for config_idx, is_valid in validation_results.items():
        status = "✓ 有效" if is_valid else "✗ 无效"
        print(f"  配置 {config_idx}: {status}")
    print()
    
    # 3. 指定配置调用示例
    print("3. 指定配置调用示例:")
    try:
        messages = [
            {"role": "user", "content": "请简单介绍一下人工智能"}
        ]
        
        # 使用配置0调用
        response = manager.call_model(
            config_index=0,
            messages=messages,
            max_tokens=100,
            temperature=0.7
        )
        
        if response and "choices" in response:
            content = response["choices"][0]["message"]["content"]
            print(f"  配置0响应: {content[:100]}...")
        
    except Exception as e:
        print(f"  调用失败: {e}")
    print()
    
    # 4. 随机调用示例
    print("4. 随机调用示例:")
    try:
        messages = [
            {"role": "user", "content": "你好，请介绍一下自己"}
        ]
        
        # 随机调用（使用所有配置）
        response = manager.random_call(
            messages=messages,
            max_tokens=50
        )
        
        if response and "choices" in response:
            content = response["choices"][0]["message"]["content"]
            print(f"  随机调用响应: {content[:80]}...")
        
    except Exception as e:
        print(f"  随机调用失败: {e}")
    print()
    
    # 5. 指定范围随机调用示例
    print("5. 指定范围随机调用示例:")
    try:
        messages = [
            {"role": "user", "content": "解释一下机器学习"}
        ]
        
        # 只在配置0和1中随机选择
        response = manager.random_call(
            messages=messages,
            config_range=[0, 1],
            max_tokens=60
        )
        
        if response and "choices" in response:
            content = response["choices"][0]["message"]["content"]
            print(f"  指定范围随机调用响应: {content[:80]}...")
        
    except Exception as e:
        print(f"  指定范围随机调用失败: {e}")
    print()
    
    # 6. 多轮对话示例
    print("6. 多轮对话示例:")
    try:
        conversation = [
            {"role": "user", "content": "你好"},
            {"role": "assistant", "content": "你好！我是AI助手，很高兴为你服务。"},
            {"role": "user", "content": "请告诉我今天的天气如何？"}
        ]
        
        response = manager.call_model(
            config_index=0,
            messages=conversation,
            max_tokens=80
        )
        
        if response and "choices" in response:
            content = response["choices"][0]["message"]["content"]
            print(f"  多轮对话响应: {content[:80]}...")
        
    except Exception as e:
        print(f"  多轮对话失败: {e}")
    

if __name__ == "__main__":
    main()