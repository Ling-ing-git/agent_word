# AI对话记录管理系统

一个支持多线程协作编辑、版本控制和智能合并的AI对话记录管理系统。

## 核心特性

### 🔄 版本控制系统
- **分支编辑**: 每个编辑会话创建独立分支，避免直接冲突
- **版本快照**: 保存完整的对话状态快照
- **历史追踪**: 完整的编辑操作历史记录

### 🤝 协作编辑
- **实时同步**: WebSocket实时同步编辑状态
- **冲突预防**: 智能锁机制和编辑意图声明
- **操作变换**: 确保并发操作的一致性

### 🧠 智能合并
- **三路合并**: 基于共同祖先的智能合并算法
- **冲突检测**: 自动检测和分类冲突严重程度
- **自动解决**: 低风险冲突的自动解决机制

## 解决的核心问题

### 1. 多线程编辑整合
```python
# 问题：多个用户同时编辑同一条消息
# 解决方案：分支编辑 + 智能合并

editor = ConversationEditor()
session1 = editor.start_collaborative_edit("user1")
session2 = editor.start_collaborative_edit("user2")

# 各自在分支中编辑
editor.edit_message_safely(session1, "msg_1", "用户1的编辑")
editor.edit_message_safely(session2, "msg_1", "用户2的编辑")

# 智能合并
result1 = editor.commit_with_smart_merge(session1)  # 直接提交
result2 = editor.commit_with_smart_merge(session2)  # 智能合并或冲突提示
```

### 2. 旧版本编辑处理
```python
# 问题：用户基于旧版本进行编辑，但原文本已更新
# 解决方案：版本检测 + 自动rebase + 三路合并

edit_result = editor.edit_message_safely(session_id, message_id, new_content)

if edit_result.get("requires_rebase"):
    # 自动处理版本冲突
    rebase_result = editor.handle_stale_edit(session_id, force_rebase=True)
    if rebase_result["success"]:
        # 重新应用编辑到最新版本
        final_result = editor.commit_with_smart_merge(rebase_result["new_session_id"])
```

### 3. 冲突解决机制
```python
# 问题：不同编辑产生冲突如何处理
# 解决方案：分层冲突解决策略

# 低严重度：自动合并
# 中等严重度：智能建议 + 用户确认
# 高严重度：手动解决

merge_result = merge_engine.intelligent_merge(base_content, v1_content, v2_content)

if merge_result.auto_resolved:
    # 自动解决成功
    apply_merge(merge_result.merged_content)
else:
    # 需要人工干预
    present_conflict_resolution_ui(merge_result.conflicts)
```

## 架构设计

### 数据结构层次
```
ConversationManager
├── VersionManager (版本控制)
│   ├── ConversationVersion (版本快照)
│   ├── EditOperation (编辑操作)
│   └── ConflictInfo (冲突信息)
├── EditSession (编辑会话)
└── ConflictResolver (冲突解决)
```

### 工作流程
1. **开始编辑** → 创建编辑分支
2. **执行编辑** → 在分支中应用操作
3. **提交更改** → 检测冲突并智能合并
4. **解决冲突** → 自动或手动解决
5. **更新主版本** → 应用最终结果

## 使用示例

### 基本使用
```python
from demo_conversation_editor import ConversationEditor

# 创建编辑器
editor = ConversationEditor()

# 初始化对话
messages = [
    {"content": "你好", "role": "user"},
    {"content": "你好！有什么可以帮助你的吗？", "role": "assistant"}
]
editor.initialize_conversation(messages)

# 开始编辑
session = editor.start_collaborative_edit("user1")

# 编辑消息
result = editor.edit_message_safely(session, "msg_1", "你好！我是AI助手，有什么可以帮助你的吗？")

# 提交更改
commit_result = editor.commit_with_smart_merge(session)
```

### 实时协作
```python
# 启动服务器
python realtime_collaboration.py server

# 客户端连接
client = CollaborationClient("user1")
await client.connect()
await client.edit_message("msg_1", "新内容")
await client.commit_changes()
```

## 运行演示

```bash
# 运行基本演示
python demo_conversation_editor.py

# 运行实时协作演示
python realtime_collaboration.py

# 启动WebSocket服务器
python realtime_collaboration.py server
```

## 扩展功能

### 1. 权限控制
- 编辑权限管理
- 审核工作流
- 角色基础访问控制

### 2. 高级合并
- 语义理解合并
- AI辅助冲突解决
- 自定义合并规则

### 3. 性能优化
- 增量同步
- 操作压缩
- 缓存策略

## 技术特点

- **线程安全**: 使用锁机制确保并发安全
- **内存效率**: 增量存储和操作记录
- **可扩展性**: 模块化设计，易于扩展
- **容错性**: 完善的错误处理和恢复机制