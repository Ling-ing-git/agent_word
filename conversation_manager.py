"""
对话管理器 - 极简版本
只有两个函数：读取和写入，自动处理版本兼容
"""

import json
import time
import threading
from typing import Dict, List, Any
from pathlib import Path

class ConversationManager:
    """对话管理器"""
    
    def __init__(self, file_path: str = "conversation.json"):
        self.file_path = file_path
        self.lock = threading.Lock()
    
    def read(self) -> List[Dict[str, Any]]:
        """读取对话记录（复制出来）"""
        with self.lock:
            try:
                if not Path(self.file_path).exists():
                    # 文件不存在，返回空对话
                    return []
                
                with open(self.file_path, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                
                # 返回消息列表的深拷贝
                if isinstance(data, dict) and "messages" in data:
                    return data["messages"].copy()
                elif isinstance(data, list):
                    return data.copy()
                else:
                    return []
                    
            except (json.JSONDecodeError, FileNotFoundError):
                return []
    
    def write(self, messages: List[Dict[str, Any]]) -> bool:
        """写入对话记录（自动版本兼容处理）"""
        with self.lock:
            try:
                # 读取当前文件内容
                current_data = self._read_current_file()
                
                # 自动版本兼容处理
                merged_messages = self._auto_merge(current_data.get("messages", []), messages)
                
                # 构建新的数据结构
                new_data = {
                    "messages": merged_messages,
                    "last_updated": time.time(),
                    "version": current_data.get("version", 0) + 1
                }
                
                # 写入文件
                with open(self.file_path, 'w', encoding='utf-8') as f:
                    json.dump(new_data, f, indent=2, ensure_ascii=False)
                
                return True
                
            except Exception as e:
                print(f"写入失败: {e}")
                return False
    
    def _read_current_file(self) -> Dict[str, Any]:
        """读取当前文件内容"""
        try:
            if not Path(self.file_path).exists():
                return {"messages": [], "version": 0}
            
            with open(self.file_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            
            # 兼容不同格式
            if isinstance(data, list):
                return {"messages": data, "version": 0}
            elif isinstance(data, dict):
                return data
            else:
                return {"messages": [], "version": 0}
                
        except:
            return {"messages": [], "version": 0}
    
    def _auto_merge(self, current_messages: List[Dict], new_messages: List[Dict]) -> List[Dict]:
        """自动合并处理版本兼容"""
        # 如果当前文件为空，直接使用新消息
        if not current_messages:
            return new_messages
        
        # 如果新消息为空，保持当前消息
        if not new_messages:
            return current_messages
        
        # 检测是否是简单的新增（末尾追加）
        if self._is_simple_append(current_messages, new_messages):
            # 简单追加新消息
            return self._merge_append(current_messages, new_messages)
        
        # 检测是否是结构重组（插入总结等）
        if self._is_structural_reorganization(current_messages, new_messages):
            # 智能合并结构变化
            return self._merge_structural(current_messages, new_messages)
        
        # 默认：使用新消息（覆盖策略）
        return new_messages
    
    def _is_simple_append(self, current: List[Dict], new: List[Dict]) -> bool:
        """检测是否为简单的末尾追加"""
        if len(new) <= len(current):
            return False
        
        # 检查前面的消息是否相同
        for i in range(len(current)):
            if i >= len(new):
                return False
            if current[i].get("content") != new[i].get("content"):
                return False
        
        return True
    
    def _is_structural_reorganization(self, current: List[Dict], new: List[Dict]) -> bool:
        """检测是否为结构重组（如插入总结）"""
        # 检查是否有消息被移动或插入了新的结构
        current_contents = [msg.get("content", "") for msg in current]
        new_contents = [msg.get("content", "") for msg in new]
        
        # 如果新版本包含了当前版本的大部分内容，但顺序或结构有变化
        current_set = set(current_contents)
        new_set = set(new_contents)
        
        # 大部分内容保留，但有新增或重组
        overlap = len(current_set.intersection(new_set))
        return overlap >= len(current_set) * 0.7  # 70%以上内容保留
    
    def _merge_append(self, current: List[Dict], new: List[Dict]) -> List[Dict]:
        """合并追加的新消息"""
        # 保留当前消息，追加新的部分
        result = current.copy()
        new_messages = new[len(current):]  # 获取新增的部分
        result.extend(new_messages)
        return result
    
    def _merge_structural(self, current: List[Dict], new: List[Dict]) -> List[Dict]:
        """合并结构重组"""
        # 检查当前版本是否有新增的消息（相比于重组版本的基础）
        current_contents = [msg.get("content", "") for msg in current]
        new_contents = [msg.get("content", "") for msg in new]
        
        # 找出当前版本中新增的消息
        new_in_current = []
        for msg in current:
            content = msg.get("content", "")
            if content not in new_contents:
                new_in_current.append(msg)
        
        # 将新增消息追加到重组后的结构
        result = new.copy()
        result.extend(new_in_current)
        
        return result

# 使用示例
if __name__ == "__main__":
    # 创建示例配置
    example_conversation = {
        "messages": [
            {"role": "user", "content": "你好"},
            {"role": "assistant", "content": "你好！有什么可以帮助你的吗？"}
        ],
        "last_updated": time.time(),
        "version": 1
    }
    
    with open("conversation.json", "w", encoding="utf-8") as f:
        json.dump(example_conversation, f, indent=2, ensure_ascii=False)
    
    # 测试读取和写入
    manager = ConversationManager()
    
    # 读取测试
    messages = manager.read()
    print("读取的对话:")
    for msg in messages:
        print(f"[{msg['role']}]: {msg['content']}")
    
    # 写入测试（追加新消息）
    new_messages = messages + [
        {"role": "user", "content": "请介绍一下Python"},
        {"role": "assistant", "content": "Python是一种高级编程语言..."}
    ]
    
    success = manager.write(new_messages)
    print(f"\n写入结果: {'成功' if success else '失败'}")
    
    # 再次读取验证
    updated_messages = manager.read()
    print(f"\n更新后的对话数量: {len(updated_messages)}")
    for msg in updated_messages:
        print(f"[{msg['role']}]: {msg['content']}")