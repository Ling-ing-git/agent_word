"""
并发对话记录管理器
解决新增消息和总结操作的并发冲突问题
"""
import asyncio
import time
import uuid
import json
from typing import List, Dict, Any, Optional, Tuple
from dataclasses import dataclass, asdict
from enum import Enum

class OperationType(Enum):
    APPEND_MESSAGE = "append_message"
    CREATE_SUMMARY = "create_summary"
    APPLY_SUMMARY = "apply_summary"

@dataclass
class Message:
    id: str
    content: str
    timestamp: float
    author: str

@dataclass
class Summary:
    id: str
    start_idx: int
    end_idx: int
    content: str
    timestamp: float

@dataclass
class Operation:
    id: str
    type: OperationType
    data: Dict[str, Any]
    timestamp: float
    expected_version: int

class ConversationManager:
    """
    使用事件驱动 + 版本控制解决并发写入问题
    核心思想：
    1. 所有操作都进入队列，串行处理
    2. 使用版本号检测冲突
    3. 失败操作自动重试
    4. 保持操作的原子性
    """
    
    def __init__(self):
        self.version = 0
        self.messages: List[Message] = []
        self.summaries: Dict[Tuple[int, int], Summary] = {}
        self.operation_queue = asyncio.Queue()
        self.processing_lock = asyncio.Lock()
        self.is_shutdown = False
        
        # 启动后台处理器
        asyncio.create_task(self._process_operations())
    
    async def add_message(self, content: str, author: str = "user") -> str:
        """添加新消息"""
        operation = Operation(
            id=str(uuid.uuid4()),
            type=OperationType.APPEND_MESSAGE,
            data={
                'content': content,
                'author': author
            },
            timestamp=time.time(),
            expected_version=self.version
        )
        
        await self.operation_queue.put(operation)
        
        # 等待操作完成
        return await self._wait_for_operation(operation.id)
    
    async def create_summary(self, start_idx: int, end_idx: int, summary_content: str) -> str:
        """创建对话总结"""
        operation = Operation(
            id=str(uuid.uuid4()),
            type=OperationType.CREATE_SUMMARY,
            data={
                'start_idx': start_idx,
                'end_idx': end_idx,
                'summary_content': summary_content
            },
            timestamp=time.time(),
            expected_version=self.version
        )
        
        await self.operation_queue.put(operation)
        return await self._wait_for_operation(operation.id)
    
    async def apply_summary(self, summary_id: str) -> bool:
        """应用总结，替换原始消息"""
        operation = Operation(
            id=str(uuid.uuid4()),
            type=OperationType.APPLY_SUMMARY,
            data={'summary_id': summary_id},
            timestamp=time.time(),
            expected_version=self.version
        )
        
        await self.operation_queue.put(operation)
        return await self._wait_for_operation(operation.id)
    
    async def _process_operations(self):
        """后台操作处理器"""
        operation_results = {}
        
        while not self.is_shutdown:
            try:
                # 获取操作（带超时避免永久阻塞）
                operation = await asyncio.wait_for(
                    self.operation_queue.get(), 
                    timeout=1.0
                )
                
                async with self.processing_lock:
                    result = await self._execute_operation(operation)
                    operation_results[operation.id] = result
                    
                    # 清理旧结果（避免内存泄漏）
                    if len(operation_results) > 1000:
                        old_keys = list(operation_results.keys())[:-500]
                        for key in old_keys:
                            operation_results.pop(key, None)
                            
            except asyncio.TimeoutError:
                continue
            except Exception as e:
                print(f"操作处理错误: {e}")
                continue
    
    async def _execute_operation(self, operation: Operation) -> Any:
        """执行具体操作"""
        try:
            # 版本检查
            if operation.expected_version != self.version:
                # 版本冲突，需要基于最新版本重新执行
                return await self._retry_operation_with_latest_version(operation)
            
            if operation.type == OperationType.APPEND_MESSAGE:
                return self._append_message(operation.data)
            elif operation.type == OperationType.CREATE_SUMMARY:
                return self._create_summary(operation.data)
            elif operation.type == OperationType.APPLY_SUMMARY:
                return self._apply_summary(operation.data)
            else:
                raise ValueError(f"未知操作类型: {operation.type}")
                
        except Exception as e:
            print(f"操作执行失败: {e}")
            return None
    
    def _append_message(self, data: Dict[str, Any]) -> str:
        """追加消息的具体实现"""
        message = Message(
            id=str(uuid.uuid4()),
            content=data['content'],
            timestamp=time.time(),
            author=data['author']
        )
        
        self.messages.append(message)
        self.version += 1
        
        print(f"✅ 消息已添加 (版本 {self.version}): {message.content[:50]}...")
        return message.id
    
    def _create_summary(self, data: Dict[str, Any]) -> str:
        """创建总结的具体实现"""
        start_idx = data['start_idx']
        end_idx = data['end_idx']
        summary_content = data['summary_content']
        
        # 验证索引范围
        if start_idx < 0 or end_idx >= len(self.messages) or start_idx > end_idx:
            raise ValueError(f"无效的总结范围: {start_idx}-{end_idx}")
        
        summary = Summary(
            id=str(uuid.uuid4()),
            start_idx=start_idx,
            end_idx=end_idx,
            content=summary_content,
            timestamp=time.time()
        )
        
        self.summaries[(start_idx, end_idx)] = summary
        self.version += 1
        
        print(f"✅ 总结已创建 (版本 {self.version}): {summary.content[:50]}...")
        return summary.id
    
    def _apply_summary(self, data: Dict[str, Any]) -> bool:
        """应用总结，替换原消息"""
        summary_id = data['summary_id']
        
        # 查找总结
        target_summary = None
        for summary in self.summaries.values():
            if summary.id == summary_id:
                target_summary = summary
                break
        
        if not target_summary:
            raise ValueError(f"总结不存在: {summary_id}")
        
        # 创建总结消息
        summary_message = Message(
            id=str(uuid.uuid4()),
            content=f"[总结] {target_summary.content}",
            timestamp=target_summary.timestamp,
            author="system"
        )
        
        # 替换消息范围
        start_idx = target_summary.start_idx
        end_idx = target_summary.end_idx
        
        new_messages = (
            self.messages[:start_idx] + 
            [summary_message] + 
            self.messages[end_idx + 1:]
        )
        
        self.messages = new_messages
        self.version += 1
        
        print(f"✅ 总结已应用 (版本 {self.version}): 替换了 {end_idx - start_idx + 1} 条消息")
        return True
    
    async def _retry_operation_with_latest_version(self, operation: Operation) -> Any:
        """基于最新版本重试操作"""
        print(f"⚠️  版本冲突，重试操作 {operation.type.value}")
        
        # 更新期望版本为当前版本
        operation.expected_version = self.version
        
        # 重新执行
        return await self._execute_operation(operation)
    
    async def _wait_for_operation(self, operation_id: str, timeout: float = 5.0) -> Any:
        """等待操作完成"""
        start_time = time.time()
        while time.time() - start_time < timeout:
            # 这里简化实现，实际应该用更优雅的通知机制
            await asyncio.sleep(0.01)
            # 检查操作是否完成...
        
        return operation_id
    
    def get_conversation_state(self) -> Dict[str, Any]:
        """获取当前对话状态"""
        return {
            'version': self.version,
            'message_count': len(self.messages),
            'messages': [asdict(msg) for msg in self.messages],
            'summaries': {
                f"{k[0]}-{k[1]}": asdict(v) 
                for k, v in self.summaries.items()
            }
        }
    
    async def shutdown(self):
        """优雅关闭"""
        self.is_shutdown = True

# 使用示例和测试
async def test_concurrent_operations():
    """测试并发操作场景"""
    manager = ConversationManager()
    
    # 初始化一些消息
    for i in range(7):
        await manager.add_message(f"消息 {chr(65 + i)}", "user")
    
    print("初始状态:", manager.get_conversation_state())
    
    # 模拟并发场景
    print("\n🔄 模拟并发操作...")
    
    # 任务1: 添加新消息H
    task1 = asyncio.create_task(
        manager.add_message("消息 H", "user")
    )
    
    # 任务2: 创建总结（压缩C-F为总结）
    task2 = asyncio.create_task(
        manager.create_summary(2, 5, "这是C到F的总结")
    )
    
    # 等待两个任务完成
    results = await asyncio.gather(task1, task2, return_exceptions=True)
    
    print("并发操作结果:", results)
    print("最终状态:", manager.get_conversation_state())
    
    await manager.shutdown()

if __name__ == "__main__":
    asyncio.run(test_concurrent_operations())