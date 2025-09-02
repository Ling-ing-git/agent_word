"""
对话管理器 - 泛用性智能写入
只有两个函数：读取和写入，自动处理所有版本兼容问题
"""

import json
import time
import threading
from typing import Dict, List, Any, Optional
from pathlib import Path
import hashlib

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
                    return []
                
                with open(self.file_path, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                
                # 兼容不同格式，返回消息列表
                if isinstance(data, dict) and "messages" in data:
                    return data["messages"].copy()
                elif isinstance(data, list):
                    return data.copy()
                else:
                    return []
                    
            except:
                return []
    
    def write(self, messages: List[Dict[str, Any]], base_version: Optional[List[Dict[str, Any]]] = None) -> bool:
        """
        智能写入对话记录 - 泛用性版本兼容处理
        
        Args:
            messages: 要写入的消息列表
            base_version: 编辑时基于的原始版本（可选，用于更精确的合并）
        
        Returns:
            bool: 写入是否成功
        """
        with self.lock:
            try:
                # 读取当前文件状态
                current_messages = self._read_raw_messages()
                
                # 如果文件为空或当前消息为空，直接写入
                if not current_messages:
                    return self._write_direct(messages)
                
                # 如果要写入的消息与当前完全相同，跳过
                if self._messages_equal(current_messages, messages):
                    return True
                
                # 智能合并处理
                merged_messages = self._intelligent_merge(current_messages, messages, base_version)
                
                # 写入合并结果
                return self._write_direct(merged_messages)
                
            except Exception as e:
                print(f"写入失败: {e}")
                return False
    
    def _read_raw_messages(self) -> List[Dict[str, Any]]:
        """读取原始消息（内部使用）"""
        try:
            if not Path(self.file_path).exists():
                return []
            
            with open(self.file_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            
            if isinstance(data, dict) and "messages" in data:
                return data["messages"]
            elif isinstance(data, list):
                return data
            else:
                return []
        except:
            return []
    
    def _write_direct(self, messages: List[Dict[str, Any]]) -> bool:
        """直接写入消息"""
        try:
            data = {
                "messages": messages,
                "last_updated": time.time(),
                "version": int(time.time() * 1000)  # 使用时间戳作为版本号
            }
            
            with open(self.file_path, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
            
            return True
        except:
            return False
    
    def _messages_equal(self, msg1: List[Dict], msg2: List[Dict]) -> bool:
        """检查两个消息列表是否相等"""
        if len(msg1) != len(msg2):
            return False
        
        for i in range(len(msg1)):
            if msg1[i].get("content") != msg2[i].get("content"):
                return False
            if msg1[i].get("role") != msg2[i].get("role"):
                return False
        
        return True
    
    def _intelligent_merge(self, current: List[Dict], new: List[Dict], base: Optional[List[Dict]]) -> List[Dict]:
        """智能合并 - 处理所有版本兼容问题"""
        
        # 如果没有基础版本，尝试推断变更类型
        if base is None:
            return self._merge_without_base(current, new)
        
        # 有基础版本，进行三方分析
        return self._merge_with_base(current, new, base)
    
    def _merge_without_base(self, current: List[Dict], new: List[Dict]) -> List[Dict]:
        """无基础版本的智能合并"""
        
        # 情况1：新版本是当前版本的超集（简单追加）
        if self._is_append_of(current, new):
            return new  # 直接使用新版本
        
        # 情况2：当前版本是新版本的超集（新版本可能是重组）
        if self._is_append_of(new, current):
            # 检测是否为结构重组
            if self._is_structural_change(new, current):
                # 保留重组结构，追加新增消息
                return self._merge_structural_with_append(new, current)
            else:
                return current  # 保持当前版本
        
        # 情况3：两者都有独特内容，需要智能合并
        return self._merge_unique_contents(current, new)
    
    def _merge_with_base(self, current: List[Dict], new: List[Dict], base: List[Dict]) -> List[Dict]:
        """基于基础版本的三方合并"""
        
        # 分析变更类型
        current_change_type = self._analyze_change_type(base, current)
        new_change_type = self._analyze_change_type(base, new)
        
        # 根据变更类型智能合并
        if current_change_type == "append" and new_change_type == "reorganize":
            # 当前是追加，新的是重组 → 保留重组结构，追加新消息
            return self._merge_reorganize_with_append(new, current, base)
        
        elif current_change_type == "reorganize" and new_change_type == "append":
            # 当前是重组，新的是追加 → 在重组基础上追加
            return self._merge_append_to_reorganize(current, new, base)
        
        elif current_change_type == "append" and new_change_type == "append":
            # 都是追加 → 合并所有新增消息
            return self._merge_both_appends(current, new, base)
        
        else:
            # 其他情况，使用启发式合并
            return self._heuristic_merge(current, new, base)
    
    def _is_append_of(self, shorter: List[Dict], longer: List[Dict]) -> bool:
        """检查shorter是否是longer的前缀"""
        if len(shorter) > len(longer):
            return False
        
        for i in range(len(shorter)):
            if not self._message_content_equal(shorter[i], longer[i]):
                return False
        
        return True
    
    def _is_structural_change(self, new: List[Dict], current: List[Dict]) -> bool:
        """检测是否为结构性变更（重组/总结）"""
        new_contents = set(msg.get("content", "") for msg in new)
        current_contents = set(msg.get("content", "") for msg in current)
        
        # 如果新版本的内容大部分存在于当前版本，但长度更短，可能是重组
        overlap = len(new_contents.intersection(current_contents))
        return len(new) < len(current) and overlap >= len(new) * 0.8
    
    def _analyze_change_type(self, base: List[Dict], changed: List[Dict]) -> str:
        """分析变更类型"""
        if len(changed) > len(base):
            # 检查是否为纯追加
            if self._is_append_of(base, changed):
                return "append"
            else:
                return "insert_and_modify"
        
        elif len(changed) < len(base):
            return "reorganize"  # 重组/删除/总结
        
        else:
            # 长度相同，检查内容变化
            if self._messages_equal(base, changed):
                return "no_change"
            else:
                return "modify"
    
    def _merge_reorganize_with_append(self, reorganized: List[Dict], appended: List[Dict], base: List[Dict]) -> List[Dict]:
        """合并重组版本和追加版本"""
        # 找出追加版本中新增的消息
        new_messages = appended[len(base):]
        
        # 将新消息追加到重组版本后
        result = reorganized.copy()
        result.extend(new_messages)
        
        return result
    
    def _merge_append_to_reorganize(self, reorganized: List[Dict], appended: List[Dict], base: List[Dict]) -> List[Dict]:
        """在重组版本基础上追加新消息"""
        # 找出追加版本中的新消息
        new_messages = appended[len(base):]
        
        # 追加到重组版本
        result = reorganized.copy()
        result.extend(new_messages)
        
        return result
    
    def _merge_both_appends(self, current: List[Dict], new: List[Dict], base: List[Dict]) -> List[Dict]:
        """合并两个都是追加的版本"""
        # 收集所有新增消息
        current_new = current[len(base):]
        new_new = new[len(base):]
        
        # 去重合并
        all_new = current_new.copy()
        for msg in new_new:
            if not any(self._message_content_equal(msg, existing) for existing in all_new):
                all_new.append(msg)
        
        # 基础版本 + 所有新增消息
        result = base.copy()
        result.extend(all_new)
        
        return result
    
    def _merge_structural_with_append(self, structural: List[Dict], appended: List[Dict]) -> List[Dict]:
        """合并结构化版本和追加版本（无基础版本）"""
        # 找出追加版本中结构化版本没有的消息
        structural_contents = set(msg.get("content", "") for msg in structural)
        unique_appended = [
            msg for msg in appended 
            if msg.get("content", "") not in structural_contents
        ]
        
        # 将独特消息追加到结构化版本
        result = structural.copy()
        result.extend(unique_appended)
        
        return result
    
    def _merge_unique_contents(self, current: List[Dict], new: List[Dict]) -> List[Dict]:
        """合并具有独特内容的两个版本"""
        # 使用内容哈希去重合并
        seen_contents = set()
        result = []
        
        # 优先保留新版本的顺序和结构
        for msg in new:
            content_hash = self._get_message_hash(msg)
            if content_hash not in seen_contents:
                result.append(msg)
                seen_contents.add(content_hash)
        
        # 添加当前版本中独有的消息
        for msg in current:
            content_hash = self._get_message_hash(msg)
            if content_hash not in seen_contents:
                result.append(msg)
                seen_contents.add(content_hash)
        
        return result
    
    def _heuristic_merge(self, current: List[Dict], new: List[Dict], base: List[Dict]) -> List[Dict]:
        """启发式合并策略"""
        # 计算各版本的"信息密度"
        current_density = len(current) / max(len(base), 1)
        new_density = len(new) / max(len(base), 1)
        
        # 如果一个版本明显更"丰富"，优先选择它作为基础
        if current_density > new_density * 1.5:
            # 当前版本更丰富，在其基础上合并新版本的独特内容
            return self._merge_into_richer_version(current, new)
        elif new_density > current_density * 1.5:
            # 新版本更丰富，在其基础上合并当前版本的独特内容
            return self._merge_into_richer_version(new, current)
        else:
            # 复杂度相近，使用内容去重合并
            return self._merge_unique_contents(current, new)
    
    def _merge_into_richer_version(self, rich_version: List[Dict], other_version: List[Dict]) -> List[Dict]:
        """将内容合并到更丰富的版本中"""
        rich_contents = set(msg.get("content", "") for msg in rich_version)
        
        # 找出其他版本的独特消息
        unique_messages = [
            msg for msg in other_version
            if msg.get("content", "") not in rich_contents
        ]
        
        # 追加到丰富版本
        result = rich_version.copy()
        result.extend(unique_messages)
        
        return result
    
    def _message_content_equal(self, msg1: Dict, msg2: Dict) -> bool:
        """检查两个消息内容是否相等"""
        return (msg1.get("content", "") == msg2.get("content", "") and 
                msg1.get("role", "") == msg2.get("role", ""))
    
    def _get_message_hash(self, msg: Dict) -> str:
        """获取消息的哈希值"""
        content = f"{msg.get('role', '')}:{msg.get('content', '')}"
        return hashlib.md5(content.encode()).hexdigest()

# 测试用例
def test_intelligent_write():
    """测试智能写入功能"""
    manager = ConversationManager("test_conversation.json")
    
    # 原始对话
    base_messages = [
        {"role": "user", "content": "A"},
        {"role": "assistant", "content": "B"},
        {"role": "user", "content": "C"},
        {"role": "assistant", "content": "D"},
        {"role": "user", "content": "E"},
        {"role": "assistant", "content": "F"},
        {"role": "user", "content": "G"}
    ]
    
    print("=== 测试智能写入 ===")
    
    # 1. 初始写入
    manager.write(base_messages)
    print("1. 初始写入完成")
    
    # 2. 模拟追加新消息 (ABCDEFG + H)
    append_messages = base_messages + [
        {"role": "assistant", "content": "H"}
    ]
    manager.write(append_messages)
    print("2. 追加消息H完成")
    
    # 3. 模拟结构重组 (AB + 总结 + G，基于原始版本)
    reorganized_messages = [
        {"role": "user", "content": "A"},
        {"role": "assistant", "content": "B"},
        {"role": "system", "content": "总结：前面讨论了基础概念"},
        {"role": "user", "content": "G"}
    ]
    
    manager.write(reorganized_messages, base_version=base_messages)
    print("3. 结构重组完成")
    
    # 4. 查看最终结果
    final_messages = manager.read()
    print(f"\n最终对话 ({len(final_messages)} 条消息):")
    for i, msg in enumerate(final_messages):
        print(f"{i+1}. [{msg['role']}]: {msg['content']}")

if __name__ == "__main__":
    test_intelligent_write()