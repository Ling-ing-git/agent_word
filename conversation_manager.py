import json
import os
from datetime import datetime
from typing import List, Dict, Any, Optional


class ConversationManager:
    """
    对话记录管理器
    负责管理conversation.json文件中的对话记录
    """
    
    def __init__(self, conversation_file: str = "conversation.json"):
        """
        初始化对话管理器
        
        Args:
            conversation_file: 对话记录文件路径
        """
        self.conversation_file = conversation_file
        self.conversations = self._load_conversations()
    
    def _load_conversations(self) -> List[Dict[str, Any]]:
        """
        加载对话记录
        
        Returns:
            对话记录列表
        """
        if not os.path.exists(self.conversation_file):
            return []
        
        try:
            with open(self.conversation_file, 'r', encoding='utf-8') as f:
                return json.load(f)
        except (json.JSONDecodeError, FileNotFoundError):
            return []
    
    def _save_conversations(self):
        """保存对话记录到文件"""
        with open(self.conversation_file, 'w', encoding='utf-8') as f:
            json.dump(self.conversations, f, ensure_ascii=False, indent=2)
    
    def add_dialogue(self, name: str, message: str, time: Optional[str] = None) -> Dict[str, Any]:
        """
        添加对话记录
        
        Args:
            name: 说话者姓名
            message: 消息内容
            time: 时间戳，默认为当前时间
            
        Returns:
            添加的对话记录
        """
        if time is None:
            time = datetime.now().strftime("%Y-%m-%d %H:%M")
        
        dialogue = {
            "type": "对话",
            "content": {
                "name": name,
                "time": time,
                "message": message
            }
        }
        
        self.conversations.append(dialogue)
        self._save_conversations()
        return dialogue
    
    def add_summary(self, summary: str, summarized_records: List[Dict[str, Any]]) -> Dict[str, Any]:
        """
        添加总结记录
        
        Args:
            summary: 总结内容
            summarized_records: 被总结的对话记录列表
            
        Returns:
            添加的总结记录
        """
        summary_record = {
            "type": "总结",
            "content": {
                "summary": summary,
                "summarized_records": summarized_records
            }
        }
        
        self.conversations.append(summary_record)
        self._save_conversations()
        return summary_record
    
    def add_operation(self, tool_name: str, result: str) -> Dict[str, Any]:
        """
        添加操作记录
        
        Args:
            tool_name: 工具名称
            result: 操作结果
            
        Returns:
            添加的操作记录
        """
        operation = {
            "type": "操作",
            "content": {
                "tool_name": tool_name,
                "result": result
            }
        }
        
        self.conversations.append(operation)
        self._save_conversations()
        return operation
    
    def get_recent_dialogues(self, count: int = 10) -> List[Dict[str, Any]]:
        """
        获取最近的对话记录
        
        Args:
            count: 获取的记录数量
            
        Returns:
            最近的对话记录列表
        """
        dialogues = [conv for conv in self.conversations if conv["type"] == "对话"]
        return dialogues[-count:] if len(dialogues) > count else dialogues
    
    def get_all_conversations(self) -> List[Dict[str, Any]]:
        """
        获取所有对话记录
        
        Returns:
            所有对话记录
        """
        return self.conversations.copy()
    
    def get_conversations_by_type(self, conv_type: str) -> List[Dict[str, Any]]:
        """
        根据类型获取对话记录
        
        Args:
            conv_type: 对话类型（对话/总结/操作）
            
        Returns:
            指定类型的对话记录列表
        """
        return [conv for conv in self.conversations if conv["type"] == conv_type]
    
    def clear_conversations(self):
        """清空所有对话记录"""
        self.conversations = []
        self._save_conversations()
    
    def format_system_records(self) -> str:
        """
        格式化系统记录，用于提示词模板
        
        Returns:
            格式化的系统记录字符串
        """
        recent_dialogues = self.get_recent_dialogues(5)
        
        if not recent_dialogues:
            return "暂无对话记录"
        
        formatted_records = []
        for dialogue in recent_dialogues:
            content = dialogue["content"]
            time_part = content["time"].split(" ")[1]  # 只取时间部分
            formatted_records.append(f"[{time_part}]{content['name']}：{content['message']}")
        
        return "\n".join(formatted_records)
    
    def get_latest_event(self) -> str:
        """
        获取最新事件，用于提示词模板
        
        Returns:
            最新事件描述
        """
        recent_dialogues = self.get_recent_dialogues(1)
        
        if not recent_dialogues:
            return "暂无最新事件"
        
        latest = recent_dialogues[0]
        content = latest["content"]
        current_time = datetime.now().strftime("%H:%M")
        
        return f'现在，{current_time}{content["name"]}说："{content["message"]}"'