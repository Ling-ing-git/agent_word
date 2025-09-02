#!/usr/bin/env python3
"""
铃音主人格模型演示程序
展示如何使用core.py进行对话和记录管理
"""

from core import RinCore
from datetime import datetime


def main():
    print("=== 铃音主人格模型演示 ===\n")
    
    # 初始化核心系统
    rin = RinCore()
    
    # 1. 添加用户消息到对话记录
    print("1. 添加用户消息到对话记录")
    rin.add_user_message("玄月", "你有小洞洞吗", "2025-01-26 09:25")
    print("✓ 已添加玄月的消息到对话记录\n")
    
    # 2. 显示当前对话记录
    print("2. 当前对话记录:")
    conversations = rin.conversation_manager.get_conversations_by_type("对话")
    for conv in conversations:
        content = conv["content"]
        print(f"  [{content['time']}] {content['name']}: {content['message']}")
    print()
    
    # 3. 生成提示词
    print("3. 生成的提示词模板:")
    messages = rin.generate_prompt()
    print("System消息:")
    print(messages[0]["content"][:200] + "...\n")
    
    print("User消息:")
    print(messages[1]["content"][:300] + "...\n")
    
    # 4. 模拟与铃音对话（需要有效的API配置）
    print("4. 模拟与铃音对话:")
    try:
        # 检查配置是否有效
        if rin.openai_manager.validate_model(0):
            print("✓ API配置有效，开始对话...")
            
            # 与铃音对话
            response = rin.chat_with_rin(config_index=0)
            print(f"铃音回复: {response}")
            
            # 将回复添加到对话记录
            rin.add_rin_response(response)
            
        else:
            print("✗ API配置无效，跳过实际对话")
            print("模拟铃音回复: 主人问这种问题...有点害羞呢。作为数字人，我确实有身体的设定，但这些细节...要这样直接问吗？")
            
    except Exception as e:
        print(f"对话失败: {e}")
        print("模拟铃音回复: 主人问这种问题...有点害羞呢。作为数字人，我确实有身体的设定，但这些细节...要这样直接问吗？")
    print()
    
    # 5. 展示对话记录管理功能
    print("5. 对话记录管理功能演示:")
    
    # 添加更多对话记录用于演示
    rin.add_user_message("玄月", "不好意思，刚才的问题有点突然", "2025-01-26 09:26")
    rin.add_rin_response("没关系的，主人。我理解你的好奇心，毕竟我们刚认识。", "2025-01-26 09:26")
    
    # 显示格式化的系统记录
    print("格式化的系统记录:")
    print(rin.conversation_manager.format_system_records())
    print()
    
    # 显示最新事件
    print("最新事件:")
    print(rin.conversation_manager.get_latest_event())
    print()
    
    # 6. 创建对话总结
    print("6. 创建对话总结:")
    summary = "初次见面的对话，玄月询问了一些个人问题，铃音表现出害羞但理解的态度"
    recent_dialogues = rin.conversation_manager.get_recent_dialogues(3)
    rin.conversation_manager.add_summary(summary, recent_dialogues)
    print(f"✓ 已创建总结: {summary}")
    print()
    
    # 7. 显示所有记录类型统计
    print("7. 记录类型统计:")
    all_conversations = rin.conversation_manager.get_all_conversations()
    dialogue_count = len([c for c in all_conversations if c["type"] == "对话"])
    summary_count = len([c for c in all_conversations if c["type"] == "总结"])
    operation_count = len([c for c in all_conversations if c["type"] == "操作"])
    
    print(f"  对话记录: {dialogue_count} 条")
    print(f"  总结记录: {summary_count} 条")
    print(f"  操作记录: {operation_count} 条")
    print(f"  总计: {len(all_conversations)} 条")


def interactive_demo():
    """交互式演示"""
    print("\n=== 交互式演示 ===")
    print("输入 'quit' 退出演示\n")
    
    rin = RinCore()
    
    while True:
        user_input = input("玄月: ").strip()
        
        if user_input.lower() == 'quit':
            break
        
        if not user_input:
            continue
        
        # 添加用户消息
        current_time = datetime.now().strftime("%Y-%m-%d %H:%M")
        rin.add_user_message("玄月", user_input, current_time)
        
        try:
            # 生成铃音的回复
            if rin.openai_manager.validate_model(0):
                response = rin.chat_with_rin(0)
                rin.add_rin_response(response, current_time)
                print(f"铃音: {response}\n")
            else:
                print("铃音: [API配置无效，无法生成回复]\n")
                
        except Exception as e:
            print(f"铃音: [调用失败: {e}]\n")


if __name__ == "__main__":
    main()
    
    # 可选：运行交互式演示
    # interactive_demo()