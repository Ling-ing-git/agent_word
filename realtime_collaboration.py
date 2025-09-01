"""
实时协作编辑系统
支持WebSocket实时同步、操作变换、冲突预防
"""

import asyncio
import websockets
import json
import uuid
import time
from typing import Dict, Set, List, Any
from dataclasses import dataclass, asdict
from demo_conversation_editor import ConversationEditor

@dataclass
class RealtimeOperation:
    """实时操作"""
    operation_id: str
    editor_id: str
    message_id: str
    operation_type: str  # edit, cursor_move, selection
    content: str
    position: int
    timestamp: float
    session_id: str

class CollaborationServer:
    """协作服务器"""
    
    def __init__(self):
        self.connected_clients: Dict[str, websockets.WebSocketServerProtocol] = {}
        self.editor_sessions: Dict[str, str] = {}  # editor_id -> session_id
        self.conversation_editor = ConversationEditor()
        self.pending_operations: List[RealtimeOperation] = []
        self.operation_lock = asyncio.Lock()
        
    async def register_client(self, websocket, editor_id: str):
        """注册客户端"""
        self.connected_clients[editor_id] = websocket
        
        # 创建编辑会话
        session_id = self.conversation_editor.start_collaborative_edit(editor_id)
        self.editor_sessions[editor_id] = session_id
        
        # 发送当前对话状态
        current_messages = self.conversation_editor.conversation_manager.get_conversation_history()
        await self.send_to_client(editor_id, {
            "type": "conversation_state",
            "messages": [
                {
                    "id": msg.id,
                    "content": msg.content,
                    "role": msg.role,
                    "timestamp": msg.timestamp
                } for msg in current_messages
            ],
            "session_id": session_id
        })
        
        print(f"客户端 {editor_id} 已连接，会话: {session_id}")
    
    async def unregister_client(self, editor_id: str):
        """注销客户端"""
        if editor_id in self.connected_clients:
            del self.connected_clients[editor_id]
        
        if editor_id in self.editor_sessions:
            # 清理编辑会话
            session_id = self.editor_sessions[editor_id]
            # 这里可以选择自动保存或丢弃未提交的编辑
            del self.editor_sessions[editor_id]
        
        print(f"客户端 {editor_id} 已断开连接")
    
    async def handle_operation(self, editor_id: str, operation_data: Dict[str, Any]):
        """处理客户端操作"""
        async with self.operation_lock:
            operation = RealtimeOperation(
                operation_id=operation_data.get("operation_id", str(uuid.uuid4())),
                editor_id=editor_id,
                message_id=operation_data["message_id"],
                operation_type=operation_data["operation_type"],
                content=operation_data.get("content", ""),
                position=operation_data.get("position", 0),
                timestamp=time.time(),
                session_id=self.editor_sessions.get(editor_id, "")
            )
            
            # 处理不同类型的操作
            if operation.operation_type == "edit":
                await self._handle_edit_operation(operation)
            elif operation.operation_type == "cursor_move":
                await self._handle_cursor_operation(operation)
            elif operation.operation_type == "selection":
                await self._handle_selection_operation(operation)
    
    async def _handle_edit_operation(self, operation: RealtimeOperation):
        """处理编辑操作"""
        # 应用编辑到会话
        result = self.conversation_editor.edit_message_safely(
            operation.session_id,
            operation.message_id,
            operation.content
        )
        
        if result["success"]:
            # 广播编辑操作到其他客户端
            await self.broadcast_operation(operation, exclude_editor=operation.editor_id)
        else:
            # 发送错误信息给编辑者
            await self.send_to_client(operation.editor_id, {
                "type": "edit_error",
                "error": result.get("error", "编辑失败"),
                "operation_id": operation.operation_id
            })
    
    async def _handle_cursor_operation(self, operation: RealtimeOperation):
        """处理光标移动"""
        # 广播光标位置到其他客户端
        await self.broadcast_to_others(operation.editor_id, {
            "type": "cursor_update",
            "editor_id": operation.editor_id,
            "message_id": operation.message_id,
            "position": operation.position,
            "timestamp": operation.timestamp
        })
    
    async def _handle_selection_operation(self, operation: RealtimeOperation):
        """处理文本选择"""
        # 广播选择状态
        await self.broadcast_to_others(operation.editor_id, {
            "type": "selection_update",
            "editor_id": operation.editor_id,
            "message_id": operation.message_id,
            "selection": operation.content,  # 选择的文本或范围
            "timestamp": operation.timestamp
        })
    
    async def send_to_client(self, editor_id: str, message: Dict[str, Any]):
        """发送消息给特定客户端"""
        if editor_id in self.connected_clients:
            try:
                await self.connected_clients[editor_id].send(json.dumps(message))
            except websockets.exceptions.ConnectionClosed:
                await self.unregister_client(editor_id)
    
    async def broadcast_to_others(self, sender_id: str, message: Dict[str, Any]):
        """广播消息给除发送者外的所有客户端"""
        for editor_id in self.connected_clients:
            if editor_id != sender_id:
                await self.send_to_client(editor_id, message)
    
    async def broadcast_operation(self, operation: RealtimeOperation, exclude_editor: str = None):
        """广播操作"""
        message = {
            "type": "operation",
            "operation": asdict(operation)
        }
        
        for editor_id in self.connected_clients:
            if editor_id != exclude_editor:
                await self.send_to_client(editor_id, message)
    
    async def handle_commit_request(self, editor_id: str):
        """处理提交请求"""
        if editor_id not in self.editor_sessions:
            await self.send_to_client(editor_id, {
                "type": "commit_error",
                "error": "无效的编辑会话"
            })
            return
        
        session_id = self.editor_sessions[editor_id]
        
        # 执行提交
        commit_result = self.conversation_editor.commit_with_smart_merge(session_id)
        
        if commit_result["success"]:
            # 提交成功，广播更新
            await self.broadcast_conversation_update()
            
            await self.send_to_client(editor_id, {
                "type": "commit_success",
                "result": commit_result
            })
        else:
            # 提交失败，发送冲突信息
            await self.send_to_client(editor_id, {
                "type": "commit_conflict",
                "conflicts": commit_result.get("conflicts", []),
                "merge_results": commit_result.get("merge_results", [])
            })
    
    async def broadcast_conversation_update(self):
        """广播对话更新"""
        current_messages = self.conversation_editor.conversation_manager.get_conversation_history()
        
        update_message = {
            "type": "conversation_updated",
            "messages": [
                {
                    "id": msg.id,
                    "content": msg.content,
                    "role": msg.role,
                    "timestamp": msg.timestamp
                } for msg in current_messages
            ],
            "timestamp": time.time()
        }
        
        for editor_id in self.connected_clients:
            await self.send_to_client(editor_id, update_message)

async def handle_client(websocket, path, server: CollaborationServer):
    """处理客户端连接"""
    editor_id = None
    
    try:
        async for message in websocket:
            data = json.loads(message)
            
            if data["type"] == "register":
                editor_id = data["editor_id"]
                await server.register_client(websocket, editor_id)
                
            elif data["type"] == "operation":
                if editor_id:
                    await server.handle_operation(editor_id, data["operation"])
                    
            elif data["type"] == "commit":
                if editor_id:
                    await server.handle_commit_request(editor_id)
                    
            elif data["type"] == "ping":
                await websocket.send(json.dumps({"type": "pong", "timestamp": time.time()}))
                
    except websockets.exceptions.ConnectionClosed:
        pass
    finally:
        if editor_id:
            await server.unregister_client(editor_id)

class ConflictPreventionSystem:
    """冲突预防系统"""
    
    def __init__(self):
        self.edit_locks: Dict[str, str] = {}  # message_id -> editor_id
        self.edit_intentions: Dict[str, List[Dict]] = {}  # message_id -> [intentions]
        
    def declare_edit_intention(self, editor_id: str, message_id: str) -> Dict[str, Any]:
        """声明编辑意图"""
        if message_id in self.edit_locks:
            current_editor = self.edit_locks[message_id]
            if current_editor != editor_id:
                return {
                    "success": False,
                    "reason": "message_locked",
                    "locked_by": current_editor,
                    "suggestion": "wait_or_collaborate"
                }
        
        # 记录编辑意图
        if message_id not in self.edit_intentions:
            self.edit_intentions[message_id] = []
        
        intention = {
            "editor_id": editor_id,
            "timestamp": time.time(),
            "status": "active"
        }
        
        self.edit_intentions[message_id].append(intention)
        
        # 如果是第一个编辑者，获得锁
        if len(self.edit_intentions[message_id]) == 1:
            self.edit_locks[message_id] = editor_id
            return {"success": True, "lock_acquired": True}
        else:
            return {
                "success": True, 
                "lock_acquired": False,
                "queue_position": len(self.edit_intentions[message_id]),
                "suggestion": "collaborative_edit"
            }
    
    def release_edit_lock(self, editor_id: str, message_id: str):
        """释放编辑锁"""
        if message_id in self.edit_locks and self.edit_locks[message_id] == editor_id:
            del self.edit_locks[message_id]
            
            # 移除编辑意图
            if message_id in self.edit_intentions:
                self.edit_intentions[message_id] = [
                    intention for intention in self.edit_intentions[message_id]
                    if intention["editor_id"] != editor_id
                ]
                
                # 如果还有其他编辑者等待，给下一个分配锁
                if self.edit_intentions[message_id]:
                    next_editor = self.edit_intentions[message_id][0]["editor_id"]
                    self.edit_locks[message_id] = next_editor
                    return next_editor
        
        return None

# WebSocket服务器启动函数
async def start_collaboration_server(host="localhost", port=8765):
    """启动协作服务器"""
    server = CollaborationServer()
    
    async def client_handler(websocket, path):
        await handle_client(websocket, path, server)
    
    print(f"启动协作服务器 ws://{host}:{port}")
    async with websockets.serve(client_handler, host, port):
        await asyncio.Future()  # 永远运行

# 客户端模拟器
class CollaborationClient:
    """协作客户端模拟器"""
    
    def __init__(self, editor_id: str):
        self.editor_id = editor_id
        self.websocket = None
        self.session_id = None
        
    async def connect(self, uri: str = "ws://localhost:8765"):
        """连接到服务器"""
        self.websocket = await websockets.connect(uri)
        
        # 注册客户端
        await self.websocket.send(json.dumps({
            "type": "register",
            "editor_id": self.editor_id
        }))
        
        print(f"[{self.editor_id}] 已连接到服务器")
        
        # 启动消息监听
        asyncio.create_task(self._listen_for_messages())
    
    async def _listen_for_messages(self):
        """监听服务器消息"""
        try:
            async for message in self.websocket:
                data = json.loads(message)
                await self._handle_server_message(data)
        except websockets.exceptions.ConnectionClosed:
            print(f"[{self.editor_id}] 与服务器连接断开")
    
    async def _handle_server_message(self, data: Dict[str, Any]):
        """处理服务器消息"""
        if data["type"] == "conversation_state":
            self.session_id = data["session_id"]
            print(f"[{self.editor_id}] 收到对话状态，会话ID: {self.session_id}")
            
        elif data["type"] == "operation":
            operation = data["operation"]
            print(f"[{self.editor_id}] 收到其他用户的操作: {operation['operation_type']} on {operation['message_id']}")
            
        elif data["type"] == "cursor_update":
            print(f"[{self.editor_id}] 用户 {data['editor_id']} 光标移动到消息 {data['message_id']} 位置 {data['position']}")
            
        elif data["type"] == "commit_success":
            print(f"[{self.editor_id}] 提交成功")
            
        elif data["type"] == "commit_conflict":
            print(f"[{self.editor_id}] 提交冲突，需要解决: {len(data['conflicts'])} 个冲突")
            
        elif data["type"] == "conversation_updated":
            print(f"[{self.editor_id}] 对话已更新")
    
    async def edit_message(self, message_id: str, new_content: str):
        """编辑消息"""
        operation = {
            "type": "operation",
            "operation": {
                "operation_id": str(uuid.uuid4()),
                "message_id": message_id,
                "operation_type": "edit",
                "content": new_content,
                "position": 0
            }
        }
        
        await self.websocket.send(json.dumps(operation))
        print(f"[{self.editor_id}] 发送编辑操作: {message_id}")
    
    async def move_cursor(self, message_id: str, position: int):
        """移动光标"""
        operation = {
            "type": "operation",
            "operation": {
                "operation_id": str(uuid.uuid4()),
                "message_id": message_id,
                "operation_type": "cursor_move",
                "position": position
            }
        }
        
        await self.websocket.send(json.dumps(operation))
    
    async def commit_changes(self):
        """提交更改"""
        await self.websocket.send(json.dumps({
            "type": "commit"
        }))
        print(f"[{self.editor_id}] 请求提交更改")
    
    async def disconnect(self):
        """断开连接"""
        if self.websocket:
            await self.websocket.close()

async def simulate_realtime_collaboration():
    """模拟实时协作场景"""
    
    print("=== 实时协作演示 ===")
    
    # 创建多个客户端
    client1 = CollaborationClient("alice")
    client2 = CollaborationClient("bob")
    client3 = CollaborationClient("charlie")
    
    # 模拟协作编辑流程
    async def alice_workflow():
        await asyncio.sleep(0.1)
        await client1.edit_message("msg_1", "这是Alice的编辑版本")
        await asyncio.sleep(0.5)
        await client1.commit_changes()
    
    async def bob_workflow():
        await asyncio.sleep(0.2)
        await client2.move_cursor("msg_1", 10)
        await asyncio.sleep(0.1)
        await client2.edit_message("msg_1", "这是Bob的编辑版本")
        await asyncio.sleep(0.3)
        await client2.commit_changes()
    
    async def charlie_workflow():
        await asyncio.sleep(0.15)
        await client3.edit_message("msg_0", "Charlie编辑了另一条消息")
        await asyncio.sleep(0.4)
        await client3.commit_changes()
    
    # 注意：这个演示需要实际的WebSocket服务器运行
    # 在实际使用中，需要先启动服务器
    print("实时协作客户端已准备就绪")
    print("要运行完整演示，请先启动WebSocket服务器")

class VersionHistory:
    """版本历史管理"""
    
    def __init__(self, conversation_manager: ConversationManager):
        self.conversation_manager = conversation_manager
        self.history_limit = 100  # 保留最近100个版本
    
    def get_version_tree(self) -> Dict[str, Any]:
        """获取版本树结构"""
        versions = self.conversation_manager.version_manager.versions
        
        tree = {
            "nodes": [],
            "edges": []
        }
        
        for version_id, version in versions.items():
            node = {
                "id": version_id,
                "timestamp": version.timestamp,
                "editor_id": version.editor_id,
                "is_merged": version.is_merged,
                "edit_count": len(version.edit_operations)
            }
            tree["nodes"].append(node)
            
            if version.parent_version:
                edge = {
                    "from": version.parent_version,
                    "to": version_id
                }
                tree["edges"].append(edge)
        
        return tree
    
    def get_message_edit_history(self, message_id: str) -> List[Dict[str, Any]]:
        """获取特定消息的编辑历史"""
        history = []
        
        for version in self.conversation_manager.version_manager.versions.values():
            for operation in version.edit_operations:
                if operation.target_message_id == message_id:
                    history.append({
                        "version_id": version.version_id,
                        "operation_id": operation.id,
                        "edit_type": operation.edit_type.value,
                        "old_content": operation.old_content,
                        "new_content": operation.new_content,
                        "timestamp": operation.timestamp,
                        "editor_id": operation.editor_id
                    })
        
        # 按时间戳排序
        history.sort(key=lambda x: x["timestamp"])
        return history
    
    def rollback_to_version(self, target_version_id: str) -> bool:
        """回滚到指定版本"""
        if target_version_id not in self.conversation_manager.version_manager.versions:
            return False
        
        # 简单实现：直接设置为主版本
        self.conversation_manager.version_manager.main_version_id = target_version_id
        return True
    
    def cleanup_old_versions(self):
        """清理旧版本"""
        versions = list(self.conversation_manager.version_manager.versions.items())
        versions.sort(key=lambda x: x[1].timestamp, reverse=True)
        
        # 保留最近的版本
        to_keep = versions[:self.history_limit]
        to_remove = versions[self.history_limit:]
        
        for version_id, _ in to_remove:
            if version_id != self.conversation_manager.version_manager.main_version_id:
                del self.conversation_manager.version_manager.versions[version_id]
        
        print(f"清理了 {len(to_remove)} 个旧版本")

# 使用示例
def demo_version_history():
    """演示版本历史功能"""
    
    print("\n=== 版本历史演示 ===")
    
    editor = ConversationEditor()
    
    # 初始化对话
    messages = [
        {"content": "Python和Java哪个更好？", "role": "user"},
        {"content": "两种语言各有优势。", "role": "assistant"}
    ]
    
    initial_version = editor.initialize_conversation(messages)
    
    # 创建版本历史管理器
    history_manager = VersionHistory(editor.conversation_manager)
    
    # 进行多次编辑
    for i in range(3):
        session = editor.start_collaborative_edit(f"editor_{i}")
        editor.edit_message_safely(session, "msg_1", f"两种语言各有优势。编辑版本 {i+1}")
        editor.commit_with_smart_merge(session)
    
    # 显示版本树
    version_tree = history_manager.get_version_tree()
    print(f"版本树节点数: {len(version_tree['nodes'])}")
    print(f"版本树边数: {len(version_tree['edges'])}")
    
    # 显示消息编辑历史
    edit_history = history_manager.get_message_edit_history("msg_1")
    print(f"\n消息 msg_1 的编辑历史 ({len(edit_history)} 次编辑):")
    for edit in edit_history:
        print(f"  - {edit['timestamp']:.2f}: {edit['editor_id']} -> {edit['new_content']}")

if __name__ == "__main__":
    import sys
    
    if len(sys.argv) > 1 and sys.argv[1] == "server":
        # 启动WebSocket服务器
        asyncio.run(start_collaboration_server())
    else:
        # 运行演示
        demo_version_history()
        asyncio.run(simulate_realtime_collaboration())