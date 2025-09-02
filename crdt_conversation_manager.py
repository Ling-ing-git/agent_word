"""
基于CRDT的对话管理器
使用Conflict-free Replicated Data Type解决并发冲突
"""
import asyncio
import time
import uuid
from typing import List, Dict, Any, Optional, Set, Tuple
from dataclasses import dataclass, field, asdict
from enum import Enum
import json

@dataclass
class VectorClock:
    """向量时钟，用于确定操作的因果关系"""
    clocks: Dict[str, int] = field(default_factory=dict)
    
    def increment(self, node_id: str):
        """递增指定节点的时钟"""
        self.clocks[node_id] = self.clocks.get(node_id, 0) + 1
    
    def update(self, other: 'VectorClock'):
        """更新向量时钟"""
        for node_id, clock in other.clocks.items():
            self.clocks[node_id] = max(self.clocks.get(node_id, 0), clock)
    
    def happens_before(self, other: 'VectorClock') -> bool:
        """判断是否发生在另一个事件之前"""
        return (all(self.clocks.get(k, 0) <= other.clocks.get(k, 0) 
                   for k in self.clocks) and
                any(self.clocks.get(k, 0) < other.clocks.get(k, 0) 
                   for k in self.clocks))
    
    def concurrent_with(self, other: 'VectorClock') -> bool:
        """判断是否与另一个事件并发"""
        return not (self.happens_before(other) or other.happens_before(self))

@dataclass
class ConversationEvent:
    """对话事件"""
    id: str
    type: str  # 'message_add', 'summary_create', 'summary_apply'
    data: Dict[str, Any]
    vector_clock: VectorClock
    node_id: str
    timestamp: float

@dataclass 
class MessageCRDT:
    """消息的CRDT表示"""
    id: str
    content: str
    author: str
    position: float  # 使用浮点数表示位置，支持任意插入
    vector_clock: VectorClock
    is_deleted: bool = False
    is_summary: bool = False

class CRDTConversationManager:
    """
    基于CRDT的对话管理器
    
    核心思想：
    1. 每个操作都有唯一的向量时钟
    2. 消息使用位置编码，支持任意位置插入
    3. 总结操作通过标记删除 + 插入新消息实现
    4. 所有操作都是可交换的，最终一致性
    """
    
    def __init__(self, node_id: str = None):
        self.node_id = node_id or str(uuid.uuid4())[:8]
        self.vector_clock = VectorClock()
        self.messages: Dict[str, MessageCRDT] = {}
        self.events: List[ConversationEvent] = []
        self.position_counter = 0.0
        
        print(f"🎯 CRDT对话管理器启动 (节点ID: {self.node_id})")
    
    async def add_message(self, content: str, author: str = "user") -> str:
        """添加消息"""
        # 递增向量时钟
        self.vector_clock.increment(self.node_id)
        
        # 生成新位置（在末尾）
        self.position_counter += 1.0
        
        message = MessageCRDT(
            id=str(uuid.uuid4()),
            content=content,
            author=author,
            position=self.position_counter,
            vector_clock=VectorClock(self.vector_clock.clocks.copy())
        )
        
        # 创建事件
        event = ConversationEvent(
            id=str(uuid.uuid4()),
            type='message_add',
            data=asdict(message),
            vector_clock=VectorClock(self.vector_clock.clocks.copy()),
            node_id=self.node_id,
            timestamp=time.time()
        )
        
        # 应用事件
        await self._apply_event(event)
        
        print(f"✅ 消息已添加 (位置 {message.position}): {content[:30]}...")
        return message.id
    
    async def create_summary(self, start_position: float, end_position: float, 
                           summary_content: str) -> str:
        """创建总结，替换指定范围的消息"""
        self.vector_clock.increment(self.node_id)
        
        # 找到需要总结的消息
        messages_to_summarize = [
            msg for msg in self.messages.values()
            if (start_position <= msg.position <= end_position and 
                not msg.is_deleted)
        ]
        
        if not messages_to_summarize:
            raise ValueError("没有找到需要总结的消息")
        
        # 计算总结插入位置（使用范围的中间位置）
        summary_position = (start_position + end_position) / 2
        
        # 创建总结消息
        summary_message = MessageCRDT(
            id=str(uuid.uuid4()),
            content=summary_content,
            author="system",
            position=summary_position,
            vector_clock=VectorClock(self.vector_clock.clocks.copy()),
            is_summary=True
        )
        
        # 创建事件：删除原消息 + 添加总结
        event = ConversationEvent(
            id=str(uuid.uuid4()),
            type='summary_create',
            data={
                'summary_message': asdict(summary_message),
                'deleted_message_ids': [msg.id for msg in messages_to_summarize],
                'range': (start_position, end_position)
            },
            vector_clock=VectorClock(self.vector_clock.clocks.copy()),
            node_id=self.node_id,
            timestamp=time.time()
        )
        
        await self._apply_event(event)
        
        print(f"✅ 总结已创建 (位置 {summary_position}): 替换了 {len(messages_to_summarize)} 条消息")
        return summary_message.id
    
    async def _apply_event(self, event: ConversationEvent):
        """应用事件到本地状态"""
        self.events.append(event)
        
        if event.type == 'message_add':
            message_data = event.data
            message = MessageCRDT(**message_data)
            self.messages[message.id] = message
            
        elif event.type == 'summary_create':
            # 添加总结消息
            summary_data = event.data['summary_message']
            summary_message = MessageCRDT(**summary_data)
            self.messages[summary_message.id] = summary_message
            
            # 标记原消息为已删除
            for msg_id in event.data['deleted_message_ids']:
                if msg_id in self.messages:
                    self.messages[msg_id].is_deleted = True
        
        # 更新向量时钟
        self.vector_clock.update(event.vector_clock)
    
    async def merge_from_other_node(self, other_events: List[ConversationEvent]):
        """合并来自其他节点的事件"""
        print(f"🔄 合并 {len(other_events)} 个外部事件...")
        
        # 按向量时钟排序事件
        sorted_events = self._sort_events_by_causality(other_events)
        
        for event in sorted_events:
            # 检查是否已经处理过这个事件
            if not any(e.id == event.id for e in self.events):
                await self._apply_event(event)
    
    def _sort_events_by_causality(self, events: List[ConversationEvent]) -> List[ConversationEvent]:
        """根据因果关系排序事件"""
        # 简化实现：按时间戳排序
        # 实际应该使用拓扑排序基于向量时钟
        return sorted(events, key=lambda e: e.timestamp)
    
    def get_ordered_messages(self) -> List[MessageCRDT]:
        """获取按位置排序的有效消息"""
        active_messages = [
            msg for msg in self.messages.values() 
            if not msg.is_deleted
        ]
        return sorted(active_messages, key=lambda m: m.position)
    
    def get_conversation_display(self) -> str:
        """获取对话显示"""
        messages = self.get_ordered_messages()
        
        lines = []
        lines.append(f"节点: {self.node_id} | 向量时钟: {self.vector_clock.clocks}")
        lines.append(f"活跃消息: {len(messages)} | 总事件: {len(self.events)}")
        lines.append("=" * 60)
        
        for i, msg in enumerate(messages):
            prefix = "📋" if msg.is_summary else "💬"
            lines.append(f"{i:2d}. {prefix} [位置:{msg.position:4.1f}] [{msg.author}] {msg.content}")
        
        return "\n".join(lines)
    
    def export_state(self) -> Dict[str, Any]:
        """导出状态用于持久化或网络传输"""
        return {
            'node_id': self.node_id,
            'vector_clock': asdict(self.vector_clock),
            'events': [asdict(event) for event in self.events],
            'position_counter': self.position_counter
        }

# 多节点并发测试
async def test_multi_node_concurrency():
    """测试多节点并发场景"""
    print("🌐 多节点并发测试...")
    
    # 创建两个节点
    node_a = CRDTConversationManager("NodeA")
    node_b = CRDTConversationManager("NodeB")
    
    # 初始同步状态
    for i, letter in enumerate("ABC"):
        await node_a.add_message(f"初始消息 {letter}", "user")
    
    # 同步到节点B
    await node_b.merge_from_other_node(node_a.events)
    
    print("\n📋 初始同步后状态:")
    print("节点A:")
    print(node_a.get_conversation_display())
    print("\n节点B:")
    print(node_b.get_conversation_display())
    
    # 模拟并发操作
    print("\n🔥 模拟节点间并发操作...")
    
    # 节点A：添加新消息
    task_a1 = asyncio.create_task(node_a.add_message("节点A的新消息D", "userA"))
    task_a2 = asyncio.create_task(node_a.add_message("节点A的新消息E", "userA"))
    
    # 节点B：创建总结 + 添加消息
    task_b1 = asyncio.create_task(node_b.create_summary(0.0, 3.0, "A-C的总结"))
    task_b2 = asyncio.create_task(node_b.add_message("节点B的新消息F", "userB"))
    
    # 等待所有操作完成
    await asyncio.gather(task_a1, task_a2, task_b1, task_b2)
    
    print("\n📋 并发操作后各节点状态:")
    print("节点A:")
    print(node_a.get_conversation_display())
    print("\n节点B:")
    print(node_b.get_conversation_display())
    
    # 交换事件并合并
    print("\n🔄 节点间事件同步...")
    
    # A的事件同步到B
    new_events_a = [e for e in node_a.events if e.node_id == "NodeA"]
    await node_b.merge_from_other_node(new_events_a)
    
    # B的事件同步到A  
    new_events_b = [e for e in node_b.events if e.node_id == "NodeB"]
    await node_a.merge_from_other_node(new_events_b)
    
    print("\n📋 最终同步后状态:")
    print("节点A:")
    print(node_a.get_conversation_display())
    print("\n节点B:")
    print(node_b.get_conversation_display())
    
    # 验证一致性
    messages_a = node_a.get_ordered_messages()
    messages_b = node_b.get_ordered_messages()
    
    print(f"\n✅ 一致性检查:")
    print(f"- 节点A消息数: {len(messages_a)}")
    print(f"- 节点B消息数: {len(messages_b)}")
    print(f"- 状态一致: {len(messages_a) == len(messages_b)}")

if __name__ == "__main__":
    asyncio.run(test_multi_node_concurrency())