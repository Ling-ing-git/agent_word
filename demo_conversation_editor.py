"""
AI对话记录编辑器演示
展示如何处理多线程编辑、版本整合、旧版本编辑等问题
"""

import time
import threading
import uuid
from conversation_version_system import *
from advanced_merge_strategies import *

class ConversationEditor:
    """对话编辑器主类"""
    
    def __init__(self):
        self.conversation_manager = ConversationManager()
        self.workflow = ConversationEditWorkflow()
        self.lock = threading.Lock()
        
    def initialize_conversation(self, messages: List[Dict[str, str]]) -> str:
        """初始化对话"""
        conv_messages = []
        for i, msg_data in enumerate(messages):
            msg = ConversationMessage(
                id=f"msg_{i}",
                content=msg_data['content'],
                role=msg_data['role'],
                timestamp=time.time() + i  # 确保时间戳递增
            )
            conv_messages.append(msg)
        
        return self.conversation_manager.version_manager.create_main_version(conv_messages)
    
    def start_collaborative_edit(self, editor_id: str) -> str:
        """开始协作编辑"""
        with self.lock:
            session_id = self.conversation_manager.start_edit_session(editor_id, "main_conversation")
            print(f"[{editor_id}] 开始编辑会话: {session_id}")
            return session_id
    
    def edit_message_safely(self, session_id: str, message_id: str, new_content: str) -> Dict[str, Any]:
        """安全地编辑消息"""
        with self.lock:
            # 检查会话是否有效
            if session_id not in self.conversation_manager.edit_sessions:
                return {"success": False, "error": "无效的编辑会话"}
            
            session = self.conversation_manager.edit_sessions[session_id]
            
            # 检查基础版本是否过期
            current_main = self.conversation_manager.version_manager.main_version_id
            if session.base_version_id != current_main:
                return {
                    "success": False, 
                    "error": "基础版本已过期",
                    "requires_rebase": True,
                    "current_version": current_main,
                    "your_base_version": session.base_version_id
                }
            
            # 执行编辑
            success = self.conversation_manager.edit_message(session_id, message_id, new_content)
            
            return {
                "success": success,
                "session_id": session_id,
                "message_id": message_id,
                "timestamp": time.time()
            }
    
    def commit_with_smart_merge(self, session_id: str) -> Dict[str, Any]:
        """智能合并提交"""
        with self.lock:
            session = self.conversation_manager.edit_sessions[session_id]
            current_main = self.conversation_manager.version_manager.main_version_id
            
            if session.base_version_id == current_main:
                # 基于最新版本，直接提交
                success, conflicts = self.conversation_manager.commit_edit_session(session_id)
                return {
                    "success": success,
                    "conflicts": conflicts,
                    "merge_type": "direct_commit"
                }
            else:
                # 需要合并，使用智能合并策略
                return self._perform_intelligent_merge(session_id)
    
    def _perform_intelligent_merge(self, session_id: str) -> Dict[str, Any]:
        """执行智能合并"""
        session = self.conversation_manager.edit_sessions[session_id]
        current_main_version = self.conversation_manager.version_manager.versions[
            self.conversation_manager.version_manager.main_version_id
        ]
        # 获取会话对应的版本ID
        session_version_id = None
        for editor_id, version_id in self.conversation_manager.version_manager.active_edit_sessions.items():
            if editor_id == session.editor_id:
                session_version_id = version_id
                break
        
        if session_version_id is None:
            # 如果找不到活跃会话，使用会话的当前版本ID
            session_version_id = session.current_version_id if hasattr(session, 'current_version_id') else session.base_version_id
        
        session_version = self.conversation_manager.version_manager.versions[session_version_id]
        base_version = self.conversation_manager.version_manager.versions[session.base_version_id]
        
        merge_results = []
        conflicts = []
        
        # 对每个被编辑的消息进行三路合并
        edited_message_ids = {op.target_message_id for op in session.pending_operations}
        
        for msg_id in edited_message_ids:
            # 获取三个版本的消息内容
            base_msg = next((msg for msg in base_version.messages if msg.id == msg_id), None)
            current_msg = next((msg for msg in current_main_version.messages if msg.id == msg_id), None)
            session_msg = next((msg for msg in session_version.messages if msg.id == msg_id), None)
            
            if not all([base_msg, current_msg, session_msg]):
                continue
            
            # 执行智能合并
            merge_result = self.workflow.merge_engine.intelligent_merge(
                base_msg.content,
                current_msg.content,
                session_msg.content
            )
            
            merge_results.append({
                'message_id': msg_id,
                'result': merge_result
            })
            
            if merge_result.has_conflicts:
                conflicts.extend(merge_result.conflicts)
        
        # 如果所有合并都成功且信心度高，自动应用
        auto_mergeable = all(
            not result['result'].has_conflicts and result['result'].confidence_score > 0.8
            for result in merge_results
        )
        
        if auto_mergeable:
            # 创建新的主版本
            new_main_messages = current_main_version.messages.copy()
            
            for merge_info in merge_results:
                msg_id = merge_info['message_id']
                merged_content = merge_info['result'].merged_content
                
                for i, msg in enumerate(new_main_messages):
                    if msg.id == msg_id:
                        new_main_messages[i] = ConversationMessage(
                            id=msg.id,
                            content=merged_content,
                            role=msg.role,
                            timestamp=msg.timestamp,
                            metadata=msg.metadata
                        )
                        break
            
            # 更新主版本
            new_version_id = str(uuid.uuid4())
            new_version = ConversationVersion(
                version_id=new_version_id,
                messages=new_main_messages,
                parent_version=current_main_version.version_id,
                timestamp=time.time(),
                editor_id="auto_merge"
            )
            
            self.conversation_manager.version_manager.versions[new_version_id] = new_version
            self.conversation_manager.version_manager.main_version_id = new_version_id
            
            # 清理会话
            self.conversation_manager._cleanup_session(session_id)
            
            return {
                "success": True,
                "merge_type": "auto_merge",
                "new_version_id": new_version_id,
                "conflicts": []
            }
        else:
            return {
                "success": False,
                "merge_type": "manual_required",
                "conflicts": conflicts,
                "merge_results": merge_results
            }
    
    def handle_stale_edit(self, session_id: str, force_rebase: bool = False) -> Dict[str, Any]:
        """处理基于旧版本的编辑"""
        session = self.conversation_manager.edit_sessions[session_id]
        current_main = self.conversation_manager.version_manager.main_version_id
        
        if session.base_version_id == current_main:
            return {"success": True, "message": "编辑基于最新版本，无需处理"}
        
        if not force_rebase:
            # 提供选项给用户
            return {
                "success": False,
                "issue": "stale_base_version",
                "options": {
                    "rebase": "重新基于最新版本进行编辑",
                    "force_merge": "强制合并（可能有冲突）",
                    "create_proposal": "创建编辑提案供审核",
                    "discard": "丢弃当前编辑"
                },
                "base_version": session.base_version_id,
                "current_version": current_main
            }
        else:
            # 执行rebase
            return self._rebase_edit_session(session_id)
    
    def _rebase_edit_session(self, session_id: str) -> Dict[str, Any]:
        """重新基于最新版本进行编辑会话"""
        session = self.conversation_manager.edit_sessions[session_id]
        
        # 保存当前的编辑操作
        pending_ops = session.pending_operations.copy()
        
        # 创建新的编辑分支基于最新版本
        new_session_id = self.conversation_manager.start_edit_session(
            session.editor_id, 
            "main_conversation"
        )
        
        # 尝试重新应用编辑操作
        successful_ops = []
        failed_ops = []
        
        for op in pending_ops:
            success = self.conversation_manager.edit_message(
                new_session_id, 
                op.target_message_id, 
                op.new_content
            )
            
            if success:
                successful_ops.append(op)
            else:
                failed_ops.append(op)
        
        # 清理旧会话
        self.conversation_manager._cleanup_session(session_id)
        
        return {
            "success": True,
            "new_session_id": new_session_id,
            "reapplied_operations": len(successful_ops),
            "failed_operations": len(failed_ops),
            "failed_ops_details": failed_ops
        }

def simulate_concurrent_editing():
    """模拟并发编辑场景"""
    
    print("=== 并发编辑演示 ===")
    
    # 创建编辑器
    editor = ConversationEditor()
    
    # 初始化对话
    initial_messages = [
        {"content": "你好，我想学习Python编程", "role": "user"},
        {"content": "好的，我来帮你学习Python。首先我们从基础语法开始。", "role": "assistant"},
        {"content": "请先教我变量和数据类型", "role": "user"},
        {"content": "Python有几种基本数据类型：整数、浮点数、字符串、布尔值。", "role": "assistant"}
    ]
    
    main_version = editor.initialize_conversation(initial_messages)
    print(f"初始化对话，主版本: {main_version}")
    
    # 模拟两个用户同时编辑
    def user1_edit():
        session1 = editor.start_collaborative_edit("user1")
        time.sleep(0.1)  # 模拟编辑时间
        
        # 用户1编辑第2条消息
        result1 = editor.edit_message_safely(session1, "msg_1", 
            "好的，我来帮你学习Python编程。首先我们从基础概念和语法开始学习。")
        print(f"[User1] 编辑结果: {result1}")
        
        time.sleep(0.2)
        
        # 用户1提交
        commit_result1 = editor.commit_with_smart_merge(session1)
        print(f"[User1] 提交结果: {commit_result1}")
    
    def user2_edit():
        time.sleep(0.05)  # 稍微延迟，模拟几乎同时开始编辑
        session2 = editor.start_collaborative_edit("user2")
        time.sleep(0.15)  # 模拟编辑时间
        
        # 用户2也编辑第2条消息
        result2 = editor.edit_message_safely(session2, "msg_1",
            "好的，我来帮你系统地学习Python。我们先从环境搭建和基础语法开始。")
        print(f"[User2] 编辑结果: {result2}")
        
        time.sleep(0.1)
        
        # 用户2提交（此时可能会遇到冲突）
        commit_result2 = editor.commit_with_smart_merge(session2)
        print(f"[User2] 提交结果: {commit_result2}")
    
    # 创建并启动线程
    thread1 = threading.Thread(target=user1_edit)
    thread2 = threading.Thread(target=user2_edit)
    
    thread1.start()
    thread2.start()
    
    thread1.join()
    thread2.join()
    
    # 显示最终结果
    print("\n=== 最终对话内容 ===")
    final_messages = editor.conversation_manager.get_conversation_history()
    for i, msg in enumerate(final_messages):
        print(f"{i+1}. [{msg.role}]: {msg.content}")

def simulate_stale_version_edit():
    """模拟基于旧版本的编辑"""
    
    print("\n=== 旧版本编辑处理演示 ===")
    
    editor = ConversationEditor()
    
    # 初始化对话
    initial_messages = [
        {"content": "如何学习机器学习？", "role": "user"},
        {"content": "学习机器学习需要掌握数学基础。", "role": "assistant"}
    ]
    
    main_version = editor.initialize_conversation(initial_messages)
    print(f"初始版本: {main_version}")
    
    # 用户1开始编辑（基于当前版本）
    session1 = editor.start_collaborative_edit("user1")
    
    # 此时用户2快速编辑并提交
    session2 = editor.start_collaborative_edit("user2")
    editor.edit_message_safely(session2, "msg_1", "学习机器学习需要掌握数学基础、编程技能和统计知识。")
    commit_result = editor.commit_with_smart_merge(session2)
    print(f"用户2快速提交: {commit_result}")
    
    # 现在用户1基于旧版本进行编辑
    edit_result = editor.edit_message_safely(session1, "msg_1", "学习机器学习需要掌握线性代数、微积分等数学基础。")
    print(f"用户1编辑结果（基于旧版本）: {edit_result}")
    
    if not edit_result.get("success") and edit_result.get("requires_rebase"):
        print("检测到基础版本过期，提供处理选项...")
        
        # 处理旧版本编辑
        stale_result = editor.handle_stale_edit(session1)
        print(f"旧版本处理选项: {stale_result}")
        
        # 选择rebase策略
        rebase_result = editor.handle_stale_edit(session1, force_rebase=True)
        print(f"Rebase结果: {rebase_result}")
        
        if rebase_result["success"]:
            # 重新提交
            new_session_id = rebase_result["new_session_id"]
            final_commit = editor.commit_with_smart_merge(new_session_id)
            print(f"重新提交结果: {final_commit}")
    
    # 显示最终结果
    print("\n最终对话内容:")
    final_messages = editor.conversation_manager.get_conversation_history()
    for i, msg in enumerate(final_messages):
        print(f"{i+1}. [{msg.role}]: {msg.content}")

class ConversationBackup:
    """对话备份和恢复"""
    
    def __init__(self, conversation_manager: ConversationManager):
        self.conversation_manager = conversation_manager
    
    def create_snapshot(self, version_id: str = None) -> Dict[str, Any]:
        """创建快照"""
        if version_id is None:
            version_id = self.conversation_manager.version_manager.main_version_id
        
        version = self.conversation_manager.version_manager.versions[version_id]
        
        snapshot = {
            "snapshot_id": str(uuid.uuid4()),
            "version_id": version_id,
            "timestamp": time.time(),
            "messages": [
                {
                    "id": msg.id,
                    "content": msg.content,
                    "role": msg.role,
                    "timestamp": msg.timestamp,
                    "metadata": msg.metadata
                } for msg in version.messages
            ],
            "edit_operations": [
                {
                    "id": op.id,
                    "edit_type": op.edit_type.value,
                    "target_message_id": op.target_message_id,
                    "old_content": op.old_content,
                    "new_content": op.new_content,
                    "timestamp": op.timestamp,
                    "editor_id": op.editor_id
                } for op in version.edit_operations
            ]
        }
        
        return snapshot
    
    def restore_from_snapshot(self, snapshot: Dict[str, Any]) -> str:
        """从快照恢复"""
        # 重建消息
        messages = []
        for msg_data in snapshot["messages"]:
            msg = ConversationMessage(
                id=msg_data["id"],
                content=msg_data["content"],
                role=msg_data["role"],
                timestamp=msg_data["timestamp"],
                metadata=msg_data["metadata"]
            )
            messages.append(msg)
        
        # 创建新版本
        restored_version_id = str(uuid.uuid4())
        restored_version = ConversationVersion(
            version_id=restored_version_id,
            messages=messages,
            parent_version=None,
            timestamp=time.time(),
            editor_id="restore_system"
        )
        
        self.conversation_manager.version_manager.versions[restored_version_id] = restored_version
        self.conversation_manager.version_manager.main_version_id = restored_version_id
        
        return restored_version_id

def demo_backup_restore():
    """演示备份和恢复功能"""
    
    print("\n=== 备份恢复演示 ===")
    
    editor = ConversationEditor()
    backup_manager = ConversationBackup(editor.conversation_manager)
    
    # 创建对话
    messages = [
        {"content": "什么是深度学习？", "role": "user"},
        {"content": "深度学习是机器学习的一个分支。", "role": "assistant"}
    ]
    
    initial_version = editor.initialize_conversation(messages)
    print(f"创建初始对话: {initial_version}")
    
    # 创建快照
    snapshot = backup_manager.create_snapshot()
    print(f"创建快照: {snapshot['snapshot_id']}")
    
    # 进行一些编辑
    session = editor.start_collaborative_edit("user1")
    editor.edit_message_safely(session, "msg_1", "深度学习是机器学习的一个重要分支，使用神经网络进行学习。")
    editor.commit_with_smart_merge(session)
    
    print("执行编辑后的对话:")
    current_messages = editor.conversation_manager.get_conversation_history()
    for msg in current_messages:
        print(f"[{msg.role}]: {msg.content}")
    
    # 恢复到快照
    restored_version = backup_manager.restore_from_snapshot(snapshot)
    print(f"\n恢复到快照: {restored_version}")
    
    print("恢复后的对话:")
    restored_messages = editor.conversation_manager.get_conversation_history()
    for msg in restored_messages:
        print(f"[{msg.role}]: {msg.content}")

if __name__ == "__main__":
    print("AI对话记录管理系统演示")
    print("=" * 50)
    
    # 运行各种演示
    simulate_concurrent_editing()
    simulate_stale_version_edit()
    demo_backup_restore()
    
    print("\n" + "=" * 50)
    print("演示完成！")