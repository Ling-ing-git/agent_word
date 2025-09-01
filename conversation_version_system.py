"""
AI对话记录管理系统 - 版本控制和协作编辑
支持多线程编辑、版本合并、冲突解决
"""

import uuid
import time
from typing import Dict, List, Optional, Any, Tuple
from dataclasses import dataclass, field
from enum import Enum
import json
import hashlib

class EditType(Enum):
    INSERT = "insert"
    DELETE = "delete" 
    MODIFY = "modify"
    MOVE = "move"

class MergeStrategy(Enum):
    AUTO = "auto"           # 自动合并
    MANUAL = "manual"       # 手动解决冲突
    LAST_WINS = "last_wins" # 最后编辑获胜
    FIRST_WINS = "first_wins" # 第一个编辑获胜

@dataclass
class ConversationMessage:
    """对话消息基本单元"""
    id: str
    content: str
    role: str  # user, assistant, system
    timestamp: float
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def __hash__(self):
        return hash(f"{self.id}:{self.content}:{self.timestamp}")

@dataclass
class EditOperation:
    """编辑操作记录"""
    id: str
    edit_type: EditType
    target_message_id: str
    old_content: Optional[str]
    new_content: Optional[str]
    position: Optional[int]  # 插入/删除位置
    timestamp: float
    editor_id: str
    parent_version: str  # 基于哪个版本进行编辑
    
    def apply_to_message(self, message: ConversationMessage) -> ConversationMessage:
        """将编辑操作应用到消息上"""
        if self.edit_type == EditType.MODIFY:
            return ConversationMessage(
                id=message.id,
                content=self.new_content,
                role=message.role,
                timestamp=message.timestamp,
                metadata=message.metadata
            )
        elif self.edit_type == EditType.INSERT:
            # 在指定位置插入文本
            content = message.content
            if self.position is not None:
                content = content[:self.position] + self.new_content + content[self.position:]
            else:
                content += self.new_content
            return ConversationMessage(
                id=message.id,
                content=content,
                role=message.role,
                timestamp=message.timestamp,
                metadata=message.metadata
            )
        elif self.edit_type == EditType.DELETE:
            # 删除指定位置的文本
            content = message.content
            if self.old_content and self.old_content in content:
                content = content.replace(self.old_content, "", 1)
            return ConversationMessage(
                id=message.id,
                content=content,
                role=message.role,
                timestamp=message.timestamp,
                metadata=message.metadata
            )
        return message

@dataclass
class ConversationVersion:
    """对话版本快照"""
    version_id: str
    messages: List[ConversationMessage]
    parent_version: Optional[str]
    timestamp: float
    editor_id: str
    edit_operations: List[EditOperation] = field(default_factory=list)
    is_merged: bool = False
    
    def get_content_hash(self) -> str:
        """获取内容哈希，用于检测冲突"""
        content = "".join([msg.content for msg in self.messages])
        return hashlib.md5(content.encode()).hexdigest()

@dataclass
class ConflictInfo:
    """冲突信息"""
    message_id: str
    conflicting_edits: List[EditOperation]
    base_content: str
    suggested_resolution: Optional[str] = None

class ConversationVersionManager:
    """对话版本管理器"""
    
    def __init__(self):
        self.versions: Dict[str, ConversationVersion] = {}
        self.main_version_id: str = None
        self.active_edit_sessions: Dict[str, str] = {}  # editor_id -> version_id
        
    def create_main_version(self, messages: List[ConversationMessage]) -> str:
        """创建主版本"""
        version_id = str(uuid.uuid4())
        version = ConversationVersion(
            version_id=version_id,
            messages=messages.copy(),
            parent_version=None,
            timestamp=time.time(),
            editor_id="system"
        )
        self.versions[version_id] = version
        self.main_version_id = version_id
        return version_id
    
    def create_edit_branch(self, editor_id: str, base_version_id: Optional[str] = None) -> str:
        """创建编辑分支"""
        if base_version_id is None:
            base_version_id = self.main_version_id
            
        base_version = self.versions[base_version_id]
        branch_id = str(uuid.uuid4())
        
        # 创建分支版本（深拷贝消息）
        branch_messages = [
            ConversationMessage(
                id=msg.id,
                content=msg.content,
                role=msg.role,
                timestamp=msg.timestamp,
                metadata=msg.metadata.copy()
            ) for msg in base_version.messages
        ]
        
        branch_version = ConversationVersion(
            version_id=branch_id,
            messages=branch_messages,
            parent_version=base_version_id,
            timestamp=time.time(),
            editor_id=editor_id
        )
        
        self.versions[branch_id] = branch_version
        self.active_edit_sessions[editor_id] = branch_id
        return branch_id
    
    def apply_edit(self, editor_id: str, edit_op: EditOperation) -> bool:
        """在编辑分支中应用编辑操作"""
        if editor_id not in self.active_edit_sessions:
            return False
            
        version_id = self.active_edit_sessions[editor_id]
        version = self.versions[version_id]
        
        # 找到目标消息
        target_message = None
        for i, msg in enumerate(version.messages):
            if msg.id == edit_op.target_message_id:
                target_message = msg
                target_index = i
                break
                
        if target_message is None:
            return False
        
        # 应用编辑操作
        edited_message = edit_op.apply_to_message(target_message)
        version.messages[target_index] = edited_message
        version.edit_operations.append(edit_op)
        
        return True
    
    def detect_conflicts(self, version1: ConversationVersion, version2: ConversationVersion) -> List[ConflictInfo]:
        """检测两个版本之间的冲突"""
        conflicts = []
        
        # 检查相同消息的不同编辑
        edited_messages_v1 = {op.target_message_id for op in version1.edit_operations}
        edited_messages_v2 = {op.target_message_id for op in version2.edit_operations}
        
        conflicting_message_ids = edited_messages_v1.intersection(edited_messages_v2)
        
        for msg_id in conflicting_message_ids:
            v1_edits = [op for op in version1.edit_operations if op.target_message_id == msg_id]
            v2_edits = [op for op in version2.edit_operations if op.target_message_id == msg_id]
            
            # 获取基础版本的消息内容
            base_version = self.versions[version1.parent_version]
            base_message = next((msg for msg in base_version.messages if msg.id == msg_id), None)
            base_content = base_message.content if base_message else ""
            
            conflict = ConflictInfo(
                message_id=msg_id,
                conflicting_edits=v1_edits + v2_edits,
                base_content=base_content
            )
            conflicts.append(conflict)
            
        return conflicts
    
    def auto_merge_versions(self, version_ids: List[str], strategy: MergeStrategy = MergeStrategy.AUTO) -> Tuple[str, List[ConflictInfo]]:
        """自动合并多个版本"""
        if len(version_ids) < 2:
            return version_ids[0] if version_ids else self.main_version_id, []
        
        # 找到共同的父版本
        base_version_id = self._find_common_ancestor(version_ids)
        base_version = self.versions[base_version_id]
        
        # 收集所有编辑操作
        all_operations = []
        for version_id in version_ids:
            version = self.versions[version_id]
            all_operations.extend(version.edit_operations)
        
        # 按时间戳排序编辑操作
        all_operations.sort(key=lambda op: op.timestamp)
        
        # 检测冲突
        conflicts = self._detect_operation_conflicts(all_operations)
        
        # 创建合并版本
        merged_version_id = str(uuid.uuid4())
        merged_messages = [
            ConversationMessage(
                id=msg.id,
                content=msg.content,
                role=msg.role,
                timestamp=msg.timestamp,
                metadata=msg.metadata.copy()
            ) for msg in base_version.messages
        ]
        
        # 应用非冲突的编辑操作
        non_conflicting_ops = [op for op in all_operations 
                              if not any(op.target_message_id == c.message_id for c in conflicts)]
        
        for op in non_conflicting_ops:
            for i, msg in enumerate(merged_messages):
                if msg.id == op.target_message_id:
                    merged_messages[i] = op.apply_to_message(msg)
                    break
        
        # 根据策略处理冲突
        if strategy == MergeStrategy.LAST_WINS:
            for conflict in conflicts:
                latest_edit = max(conflict.conflicting_edits, key=lambda op: op.timestamp)
                for i, msg in enumerate(merged_messages):
                    if msg.id == conflict.message_id:
                        merged_messages[i] = latest_edit.apply_to_message(msg)
                        break
            conflicts = []  # 冲突已解决
        
        merged_version = ConversationVersion(
            version_id=merged_version_id,
            messages=merged_messages,
            parent_version=base_version_id,
            timestamp=time.time(),
            editor_id="system_merge",
            edit_operations=all_operations,
            is_merged=True
        )
        
        self.versions[merged_version_id] = merged_version
        return merged_version_id, conflicts
    
    def _find_common_ancestor(self, version_ids: List[str]) -> str:
        """找到版本的共同祖先"""
        if not version_ids:
            return self.main_version_id
            
        # 简化实现：返回最早的父版本
        ancestors = []
        for version_id in version_ids:
            version = self.versions[version_id]
            if version.parent_version:
                ancestors.append(version.parent_version)
        
        return ancestors[0] if ancestors else self.main_version_id
    
    def _detect_operation_conflicts(self, operations: List[EditOperation]) -> List[ConflictInfo]:
        """检测编辑操作之间的冲突"""
        conflicts = []
        message_edits = {}
        
        # 按消息ID分组编辑操作
        for op in operations:
            if op.target_message_id not in message_edits:
                message_edits[op.target_message_id] = []
            message_edits[op.target_message_id].append(op)
        
        # 检测每个消息的冲突编辑
        for msg_id, edits in message_edits.items():
            if len(edits) > 1:
                # 检查是否真的冲突（不同的编辑内容）
                unique_edits = []
                for edit in edits:
                    if not any(e.new_content == edit.new_content for e in unique_edits):
                        unique_edits.append(edit)
                
                if len(unique_edits) > 1:
                    conflict = ConflictInfo(
                        message_id=msg_id,
                        conflicting_edits=unique_edits,
                        base_content=""  # 需要从父版本获取
                    )
                    conflicts.append(conflict)
        
        return conflicts
    
    def create_diff(self, version1_id: str, version2_id: str) -> Dict[str, Any]:
        """创建两个版本之间的差异"""
        v1 = self.versions[version1_id]
        v2 = self.versions[version2_id]
        
        diff = {
            "added_messages": [],
            "removed_messages": [],
            "modified_messages": [],
            "metadata": {
                "version1": version1_id,
                "version2": version2_id,
                "timestamp": time.time()
            }
        }
        
        v1_msg_dict = {msg.id: msg for msg in v1.messages}
        v2_msg_dict = {msg.id: msg for msg in v2.messages}
        
        # 检查新增和修改的消息
        for msg_id, msg in v2_msg_dict.items():
            if msg_id not in v1_msg_dict:
                diff["added_messages"].append(msg)
            elif v1_msg_dict[msg_id].content != msg.content:
                diff["modified_messages"].append({
                    "message_id": msg_id,
                    "old_content": v1_msg_dict[msg_id].content,
                    "new_content": msg.content
                })
        
        # 检查删除的消息
        for msg_id, msg in v1_msg_dict.items():
            if msg_id not in v2_msg_dict:
                diff["removed_messages"].append(msg)
        
        return diff

class ConflictResolver:
    """冲突解决器"""
    
    @staticmethod
    def three_way_merge(base_content: str, version1_content: str, version2_content: str) -> Tuple[str, bool]:
        """三路合并算法"""
        # 简化的三路合并实现
        if version1_content == version2_content:
            return version1_content, True  # 无冲突
        
        if version1_content == base_content:
            return version2_content, True  # version2的更改
        
        if version2_content == base_content:
            return version1_content, True  # version1的更改
        
        # 存在冲突，返回标记的冲突内容
        conflict_marker = f"""<<<<<<< Version 1
{version1_content}
=======
{version2_content}
>>>>>>> Version 2"""
        
        return conflict_marker, False
    
    @staticmethod
    def smart_text_merge(base: str, v1: str, v2: str) -> Tuple[str, bool]:
        """智能文本合并（基于行差异）"""
        base_lines = base.split('\n')
        v1_lines = v1.split('\n')
        v2_lines = v2.split('\n')
        
        # 使用简单的最长公共子序列算法
        # 这里可以集成更复杂的diff算法如Myers算法
        
        # 简化实现：如果只有一方修改，采用修改后的版本
        if v1_lines == base_lines:
            return v2, True
        elif v2_lines == base_lines:
            return v1, True
        else:
            # 复杂冲突，需要手动解决
            return ConflictResolver.three_way_merge(base, v1, v2)

class EditSession:
    """编辑会话管理"""
    
    def __init__(self, session_id: str, editor_id: str, base_version_id: str):
        self.session_id = session_id
        self.editor_id = editor_id
        self.base_version_id = base_version_id
        self.current_version_id = base_version_id
        self.pending_operations: List[EditOperation] = []
        self.is_active = True
        self.last_activity = time.time()
    
    def add_operation(self, operation: EditOperation):
        """添加编辑操作"""
        self.pending_operations.append(operation)
        self.last_activity = time.time()
    
    def is_stale(self, timeout_seconds: int = 3600) -> bool:
        """检查会话是否过期"""
        return time.time() - self.last_activity > timeout_seconds

class ConversationManager:
    """对话管理器主类"""
    
    def __init__(self):
        self.version_manager = ConversationVersionManager()
        self.conflict_resolver = ConflictResolver()
        self.edit_sessions: Dict[str, EditSession] = {}
        
    def start_edit_session(self, editor_id: str, conversation_id: str) -> str:
        """开始编辑会话"""
        # 创建编辑分支
        branch_id = self.version_manager.create_edit_branch(editor_id)
        
        # 创建编辑会话
        session_id = str(uuid.uuid4())
        session = EditSession(session_id, editor_id, branch_id)
        self.edit_sessions[session_id] = session
        
        return session_id
    
    def edit_message(self, session_id: str, message_id: str, new_content: str) -> bool:
        """编辑消息内容"""
        if session_id not in self.edit_sessions:
            return False
            
        session = self.edit_sessions[session_id]
        
        # 创建编辑操作
        edit_op = EditOperation(
            id=str(uuid.uuid4()),
            edit_type=EditType.MODIFY,
            target_message_id=message_id,
            old_content=None,  # 可以从当前版本获取
            new_content=new_content,
            position=None,
            timestamp=time.time(),
            editor_id=session.editor_id,
            parent_version=session.base_version_id
        )
        
        # 应用到版本管理器
        success = self.version_manager.apply_edit(session.editor_id, edit_op)
        if success:
            session.add_operation(edit_op)
        
        return success
    
    def commit_edit_session(self, session_id: str, merge_strategy: MergeStrategy = MergeStrategy.AUTO) -> Tuple[bool, List[ConflictInfo]]:
        """提交编辑会话"""
        if session_id not in self.edit_sessions:
            return False, []
        
        session = self.edit_sessions[session_id]
        
        # 检查基础版本是否仍然是最新的
        current_main = self.version_manager.main_version_id
        if session.base_version_id != current_main:
            # 需要合并
            merged_version_id, conflicts = self.version_manager.auto_merge_versions(
                [session.current_version_id, current_main], 
                strategy=merge_strategy
            )
            
            if not conflicts:
                # 合并成功，更新主版本
                self.version_manager.main_version_id = merged_version_id
                self._cleanup_session(session_id)
                return True, []
            else:
                # 存在冲突，需要解决
                return False, conflicts
        else:
            # 直接更新主版本
            self.version_manager.main_version_id = session.current_version_id
            self._cleanup_session(session_id)
            return True, []
    
    def resolve_conflict(self, conflict: ConflictInfo, resolution_content: str) -> bool:
        """手动解决冲突"""
        # 创建解决冲突的编辑操作
        resolution_op = EditOperation(
            id=str(uuid.uuid4()),
            edit_type=EditType.MODIFY,
            target_message_id=conflict.message_id,
            old_content=None,
            new_content=resolution_content,
            position=None,
            timestamp=time.time(),
            editor_id="conflict_resolver",
            parent_version=self.version_manager.main_version_id
        )
        
        # 应用解决方案到主版本
        return self.version_manager.apply_edit("conflict_resolver", resolution_op)
    
    def _cleanup_session(self, session_id: str):
        """清理编辑会话"""
        if session_id in self.edit_sessions:
            session = self.edit_sessions[session_id]
            if session.editor_id in self.version_manager.active_edit_sessions:
                del self.version_manager.active_edit_sessions[session.editor_id]
            del self.edit_sessions[session_id]
    
    def get_conversation_history(self, version_id: Optional[str] = None) -> List[ConversationMessage]:
        """获取对话历史"""
        if version_id is None:
            version_id = self.version_manager.main_version_id
        
        if version_id in self.version_manager.versions:
            return self.version_manager.versions[version_id].messages
        return []
    
    def cleanup_stale_sessions(self, timeout_seconds: int = 3600):
        """清理过期的编辑会话"""
        stale_sessions = [
            session_id for session_id, session in self.edit_sessions.items()
            if session.is_stale(timeout_seconds)
        ]
        
        for session_id in stale_sessions:
            self._cleanup_session(session_id)

# 使用示例和测试
if __name__ == "__main__":
    # 创建对话管理器
    manager = ConversationManager()
    
    # 创建初始对话
    initial_messages = [
        ConversationMessage("msg1", "你好，我是AI助手", "assistant", time.time()),
        ConversationMessage("msg2", "请帮我写一个Python函数", "user", time.time()),
        ConversationMessage("msg3", "好的，我来帮你写一个函数", "assistant", time.time())
    ]
    
    main_version = manager.version_manager.create_main_version(initial_messages)
    print(f"创建主版本: {main_version}")
    
    # 模拟两个用户同时编辑
    session1 = manager.start_edit_session("user1", "conv1")
    session2 = manager.start_edit_session("user2", "conv1")
    
    print(f"用户1编辑会话: {session1}")
    print(f"用户2编辑会话: {session2}")
    
    # 用户1编辑消息
    manager.edit_message(session1, "msg3", "好的，我来帮你写一个排序函数")
    
    # 用户2也编辑相同消息
    manager.edit_message(session2, "msg3", "好的，我来帮你写一个搜索函数")
    
    # 用户1先提交
    success1, conflicts1 = manager.commit_edit_session(session1)
    print(f"用户1提交结果: {success1}, 冲突: {len(conflicts1)}")
    
    # 用户2后提交（会产生冲突）
    success2, conflicts2 = manager.commit_edit_session(session2)
    print(f"用户2提交结果: {success2}, 冲突: {len(conflicts2)}")
    
    if conflicts2:
        print("检测到冲突，需要解决:")
        for conflict in conflicts2:
            print(f"消息ID: {conflict.message_id}")
            print("冲突的编辑:")
            for edit in conflict.conflicting_edits:
                print(f"  - {edit.editor_id}: {edit.new_content}")
        
        # 手动解决冲突
        resolution = "好的，我来帮你写一个排序和搜索函数"
        manager.resolve_conflict(conflicts2[0], resolution)
        print(f"冲突已解决: {resolution}")
    
    # 显示最终结果
    final_messages = manager.get_conversation_history()
    print("\n最终对话内容:")
    for msg in final_messages:
        print(f"{msg.role}: {msg.content}")