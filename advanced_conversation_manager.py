"""
高级并发对话管理器
使用操作合并和冲突解决策略
"""
import asyncio
import time
import uuid
import json
from typing import List, Dict, Any, Optional, Tuple, Union
from dataclasses import dataclass, asdict
from enum import Enum
import copy

class OperationType(Enum):
    APPEND_MESSAGE = "append_message"
    CREATE_SUMMARY = "create_summary"
    BATCH_OPERATIONS = "batch_operations"

@dataclass
class Message:
    id: str
    content: str
    timestamp: float
    author: str
    is_summary: bool = False

@dataclass
class ConversationState:
    version: int
    messages: List[Message]
    last_modified: float

class ConflictResolver:
    """冲突解决器"""
    
    @staticmethod
    def can_merge_operations(op1: Dict, op2: Dict) -> bool:
        """判断两个操作是否可以合并"""
        # 如果都是追加消息，可以合并
        if (op1['type'] == OperationType.APPEND_MESSAGE and 
            op2['type'] == OperationType.APPEND_MESSAGE):
            return True
        
        # 如果一个是追加，一个是总结，需要检查是否有重叠
        if op1['type'] == OperationType.APPEND_MESSAGE and op2['type'] == OperationType.CREATE_SUMMARY:
            return True  # 追加不影响总结的历史范围
        
        if op1['type'] == OperationType.CREATE_SUMMARY and op2['type'] == OperationType.APPEND_MESSAGE:
            return True  # 同上
        
        return False
    
    @staticmethod
    def merge_operations(ops: List[Dict]) -> Dict:
        """合并兼容的操作"""
        if not ops:
            return None
        
        if len(ops) == 1:
            return ops[0]
        
        # 分离不同类型的操作
        append_ops = [op for op in ops if op['type'] == OperationType.APPEND_MESSAGE]
        summary_ops = [op for op in ops if op['type'] == OperationType.CREATE_SUMMARY]
        
        merged_operations = []
        
        # 合并所有追加操作
        if append_ops:
            merged_messages = []
            for op in append_ops:
                merged_messages.append(op['data'])
            
            merged_operations.append({
                'id': str(uuid.uuid4()),
                'type': OperationType.APPEND_MESSAGE,
                'data': merged_messages,  # 批量消息
                'timestamp': max(op['timestamp'] for op in append_ops),
                'expected_version': max(op['expected_version'] for op in append_ops)
            })
        
        # 保持总结操作不变（按时间顺序）
        merged_operations.extend(sorted(summary_ops, key=lambda x: x['timestamp']))
        
        return {
            'id': str(uuid.uuid4()),
            'type': OperationType.BATCH_OPERATIONS,
            'data': merged_operations,
            'timestamp': time.time(),
            'expected_version': max(op['expected_version'] for op in ops)
        }

class AdvancedConversationManager:
    """
    高级对话管理器，支持智能冲突解决
    """
    
    def __init__(self, batch_timeout: float = 0.1):
        self.state = ConversationState(
            version=0,
            messages=[],
            last_modified=time.time()
        )
        self.pending_operations: List[Dict] = []
        self.batch_timeout = batch_timeout
        self.operation_results: Dict[str, Any] = {}
        self.result_events: Dict[str, asyncio.Event] = {}
        
        # 启动批处理器
        asyncio.create_task(self._batch_processor())
    
    async def add_message(self, content: str, author: str = "user") -> str:
        """添加新消息"""
        operation_id = str(uuid.uuid4())
        operation = {
            'id': operation_id,
            'type': OperationType.APPEND_MESSAGE,
            'data': {
                'content': content,
                'author': author
            },
            'timestamp': time.time(),
            'expected_version': self.state.version
        }
        
        # 创建结果等待事件
        self.result_events[operation_id] = asyncio.Event()
        
        # 添加到待处理队列
        self.pending_operations.append(operation)
        
        # 等待结果
        await self.result_events[operation_id].wait()
        result = self.operation_results.get(operation_id)
        
        # 清理
        self.result_events.pop(operation_id, None)
        self.operation_results.pop(operation_id, None)
        
        return result
    
    async def create_summary(self, start_idx: int, end_idx: int, summary_content: str) -> str:
        """创建并应用总结"""
        operation_id = str(uuid.uuid4())
        operation = {
            'id': operation_id,
            'type': OperationType.CREATE_SUMMARY,
            'data': {
                'start_idx': start_idx,
                'end_idx': end_idx,
                'summary_content': summary_content
            },
            'timestamp': time.time(),
            'expected_version': self.state.version
        }
        
        self.result_events[operation_id] = asyncio.Event()
        self.pending_operations.append(operation)
        
        await self.result_events[operation_id].wait()
        result = self.operation_results.get(operation_id)
        
        # 清理
        self.result_events.pop(operation_id, None)
        self.operation_results.pop(operation_id, None)
        
        return result
    
    async def _batch_processor(self):
        """批处理器：收集一段时间内的操作，然后批量处理"""
        while True:
            if not self.pending_operations:
                await asyncio.sleep(0.01)
                continue
            
            # 等待批处理超时时间
            await asyncio.sleep(self.batch_timeout)
            
            if not self.pending_operations:
                continue
            
            # 获取当前批次的操作
            current_batch = self.pending_operations.copy()
            self.pending_operations.clear()
            
            print(f"🔄 处理批次: {len(current_batch)} 个操作")
            
            # 尝试合并兼容的操作
            merged_operations = self._merge_compatible_operations(current_batch)
            
            # 执行合并后的操作
            for operation in merged_operations:
                try:
                    result = await self._execute_single_operation(operation)
                    
                    # 如果是批量操作，需要分发结果给原始操作
                    if operation['type'] == OperationType.BATCH_OPERATIONS:
                        self._distribute_batch_results(operation, result)
                    else:
                        # 单个操作结果
                        self.operation_results[operation['id']] = result
                        if operation['id'] in self.result_events:
                            self.result_events[operation['id']].set()
                            
                except Exception as e:
                    print(f"❌ 操作执行失败: {e}")
                    # 设置错误结果
                    self.operation_results[operation['id']] = None
                    if operation['id'] in self.result_events:
                        self.result_events[operation['id']].set()
    
    def _merge_compatible_operations(self, operations: List[Dict]) -> List[Dict]:
        """合并兼容的操作"""
        if len(operations) <= 1:
            return operations
        
        # 按类型分组
        append_ops = [op for op in operations if op['type'] == OperationType.APPEND_MESSAGE]
        summary_ops = [op for op in operations if op['type'] == OperationType.CREATE_SUMMARY]
        
        merged = []
        
        # 如果有多个追加操作，合并它们
        if len(append_ops) > 1:
            print(f"🔗 合并 {len(append_ops)} 个追加操作")
            merged_op = ConflictResolver.merge_operations(append_ops)
            merged_op['original_ops'] = append_ops  # 保存原始操作信息
            merged.append(merged_op)
        elif append_ops:
            merged.extend(append_ops)
        
        # 总结操作按时间顺序执行
        if summary_ops:
            merged.extend(sorted(summary_ops, key=lambda x: x['timestamp']))
        
        return merged
    
    async def _execute_single_operation(self, operation: Dict) -> Any:
        """执行单个操作"""
        if operation['type'] == OperationType.BATCH_OPERATIONS:
            return await self._execute_batch_operation(operation)
        elif operation['type'] == OperationType.APPEND_MESSAGE:
            # 检查是否是批量消息
            if isinstance(operation['data'], list):
                return self._append_multiple_messages(operation['data'])
            else:
                return self._append_single_message(operation['data'])
        elif operation['type'] == OperationType.CREATE_SUMMARY:
            return self._create_and_apply_summary(operation['data'])
        
        raise ValueError(f"未知操作类型: {operation['type']}")
    
    def _append_single_message(self, data: Dict) -> str:
        """追加单个消息"""
        message = Message(
            id=str(uuid.uuid4()),
            content=data['content'],
            timestamp=time.time(),
            author=data['author']
        )
        
        self.state.messages.append(message)
        self.state.version += 1
        self.state.last_modified = time.time()
        
        return message.id
    
    def _append_multiple_messages(self, messages_data: List[Dict]) -> List[str]:
        """批量追加消息"""
        message_ids = []
        
        for data in messages_data:
            message = Message(
                id=str(uuid.uuid4()),
                content=data['content'],
                timestamp=time.time(),
                author=data['author']
            )
            self.state.messages.append(message)
            message_ids.append(message.id)
        
        self.state.version += 1
        self.state.last_modified = time.time()
        
        print(f"✅ 批量添加了 {len(message_ids)} 条消息")
        return message_ids
    
    def _create_and_apply_summary(self, data: Dict) -> str:
        """创建并立即应用总结"""
        start_idx = data['start_idx']
        end_idx = data['end_idx']
        summary_content = data['summary_content']
        
        # 验证索引（考虑可能的新增消息）
        if start_idx < 0 or end_idx >= len(self.state.messages):
            # 调整索引范围
            end_idx = min(end_idx, len(self.state.messages) - 1)
            print(f"⚠️  调整总结范围: {start_idx}-{end_idx}")
        
        if start_idx > end_idx:
            raise ValueError(f"无效的总结范围: {start_idx}-{end_idx}")
        
        # 创建总结消息
        summary_message = Message(
            id=str(uuid.uuid4()),
            content=f"[总结] {summary_content}",
            timestamp=time.time(),
            author="system",
            is_summary=True
        )
        
        # 替换消息范围
        new_messages = (
            self.state.messages[:start_idx] + 
            [summary_message] + 
            self.state.messages[end_idx + 1:]
        )
        
        self.state.messages = new_messages
        self.state.version += 1
        self.state.last_modified = time.time()
        
        print(f"✅ 总结已应用: 替换了 {end_idx - start_idx + 1} 条消息")
        return summary_message.id
    
    async def _execute_batch_operation(self, operation: Dict) -> List[Any]:
        """执行批量操作"""
        results = []
        for sub_op in operation['data']:
            result = await self._execute_single_operation(sub_op)
            results.append(result)
        return results
    
    def _distribute_batch_results(self, batch_operation: Dict, results: List[Any]):
        """分发批量操作的结果给原始操作"""
        if 'original_ops' not in batch_operation:
            return
        
        original_ops = batch_operation['original_ops']
        
        # 为每个原始操作设置结果
        for i, original_op in enumerate(original_ops):
            if i < len(results):
                self.operation_results[original_op['id']] = results[i]
            else:
                self.operation_results[original_op['id']] = None
            
            # 触发等待事件
            if original_op['id'] in self.result_events:
                self.result_events[original_op['id']].set()
    
    def get_conversation_display(self) -> str:
        """获取对话的显示格式"""
        lines = []
        lines.append(f"对话版本: {self.state.version}")
        lines.append(f"消息数量: {len(self.state.messages)}")
        lines.append("=" * 50)
        
        for i, msg in enumerate(self.state.messages):
            prefix = "📝" if msg.is_summary else "💬"
            lines.append(f"{i:2d}. {prefix} [{msg.author}] {msg.content}")
        
        return "\n".join(lines)

# 实际使用示例
async def demonstrate_conflict_resolution():
    """演示冲突解决机制"""
    manager = AdvancedConversationManager(batch_timeout=0.05)  # 50ms批处理窗口
    
    # 初始化对话
    print("🚀 初始化对话...")
    for i, letter in enumerate("ABCDEFG"):
        await manager.add_message(f"消息 {letter}: 这是第{i+1}条消息", "user")
    
    print("\n📋 初始对话状态:")
    print(manager.get_conversation_display())
    
    print("\n🔥 模拟高并发场景...")
    
    # 创建多个并发任务
    tasks = []
    
    # 任务组1: 同时添加多条新消息
    for letter in "HIJ":
        task = asyncio.create_task(
            manager.add_message(f"消息 {letter}: 新增的消息", "user")
        )
        tasks.append(task)
    
    # 任务组2: 同时创建总结
    summary_task1 = asyncio.create_task(
        manager.create_summary(1, 3, "B-D的总结：讨论了前期话题")
    )
    tasks.append(summary_task1)
    
    summary_task2 = asyncio.create_task(
        manager.create_summary(4, 6, "E-G的总结：讨论了后期话题")  
    )
    tasks.append(summary_task2)
    
    # 等待所有任务完成
    print("⏳ 等待所有并发操作完成...")
    results = await asyncio.gather(*tasks, return_exceptions=True)
    
    print(f"\n✅ 所有操作完成，结果: {len([r for r in results if not isinstance(r, Exception)])} 成功")
    
    print("\n📋 最终对话状态:")
    print(manager.get_conversation_display())
    
    # 显示操作统计
    print(f"\n📊 状态统计:")
    print(f"- 最终版本: {manager.state.version}")
    print(f"- 消息总数: {len(manager.state.messages)}")
    print(f"- 总结消息数: {sum(1 for msg in manager.state.messages if msg.is_summary)}")

# 性能测试
async def performance_test():
    """性能测试：大量并发操作"""
    print("\n🏃‍♂️ 性能测试开始...")
    manager = AdvancedConversationManager(batch_timeout=0.02)
    
    start_time = time.time()
    
    # 创建大量并发任务
    tasks = []
    
    # 100个并发消息添加
    for i in range(100):
        task = asyncio.create_task(
            manager.add_message(f"性能测试消息 {i}", "test_user")
        )
        tasks.append(task)
    
    # 10个并发总结
    for i in range(10):
        start_idx = i * 10
        end_idx = min(start_idx + 5, 99)
        task = asyncio.create_task(
            manager.create_summary(start_idx, end_idx, f"总结 {i}")
        )
        tasks.append(task)
    
    # 等待完成
    results = await asyncio.gather(*tasks, return_exceptions=True)
    
    end_time = time.time()
    
    print(f"⚡ 性能测试完成:")
    print(f"- 总耗时: {end_time - start_time:.3f}s")
    print(f"- 总操作数: {len(tasks)}")
    print(f"- 成功操作: {len([r for r in results if not isinstance(r, Exception)])}")
    print(f"- 最终版本: {manager.state.version}")
    print(f"- 平均每操作耗时: {(end_time - start_time) / len(tasks) * 1000:.2f}ms")

if __name__ == "__main__":
    async def main():
        await demonstrate_conflict_resolution()
        await performance_test()
    
    asyncio.run(main())