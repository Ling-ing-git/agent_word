"""
高级合并策略和冲突解决机制
包含智能文本合并、语义理解、自动冲突解决
"""

import difflib
import re
from typing import List, Dict, Any, Tuple, Optional
from dataclasses import dataclass
from enum import Enum
import json

class ConflictSeverity(Enum):
    LOW = "low"           # 可自动解决
    MEDIUM = "medium"     # 建议人工审核
    HIGH = "high"         # 必须人工解决

@dataclass
class TextSegment:
    """文本片段"""
    content: str
    start_pos: int
    end_pos: int
    type: str  # original, added, deleted, modified

@dataclass
class MergeResult:
    """合并结果"""
    merged_content: str
    has_conflicts: bool
    conflicts: List[Dict[str, Any]]
    confidence_score: float  # 0-1，合并的信心度
    auto_resolved: bool

class AdvancedMergeEngine:
    """高级合并引擎"""
    
    def __init__(self):
        self.merge_rules = self._load_merge_rules()
    
    def _load_merge_rules(self) -> Dict[str, Any]:
        """加载合并规则"""
        return {
            "preserve_formatting": True,
            "smart_line_merge": True,
            "semantic_analysis": True,
            "auto_resolve_threshold": 0.8
        }
    
    def intelligent_merge(self, base_content: str, version1_content: str, version2_content: str) -> MergeResult:
        """智能合并三个版本的内容"""
        
        # 1. 预处理 - 标准化格式
        base_normalized = self._normalize_text(base_content)
        v1_normalized = self._normalize_text(version1_content)
        v2_normalized = self._normalize_text(version2_content)
        
        # 2. 计算差异
        base_to_v1_diff = list(difflib.unified_diff(
            base_normalized.splitlines(keepends=True),
            v1_normalized.splitlines(keepends=True),
            lineterm=''
        ))
        
        base_to_v2_diff = list(difflib.unified_diff(
            base_normalized.splitlines(keepends=True),
            v2_normalized.splitlines(keepends=True),
            lineterm=''
        ))
        
        # 3. 分析变更类型
        v1_changes = self._analyze_changes(base_to_v1_diff)
        v2_changes = self._analyze_changes(base_to_v2_diff)
        
        # 4. 检测冲突
        conflicts = self._detect_semantic_conflicts(v1_changes, v2_changes, base_content)
        
        # 5. 执行合并
        if not conflicts:
            # 无冲突，直接合并
            merged_content = self._apply_non_conflicting_changes(base_content, v1_changes, v2_changes)
            return MergeResult(
                merged_content=merged_content,
                has_conflicts=False,
                conflicts=[],
                confidence_score=1.0,
                auto_resolved=True
            )
        else:
            # 有冲突，尝试智能解决
            return self._resolve_conflicts_intelligently(base_content, v1_changes, v2_changes, conflicts)
    
    def _normalize_text(self, text: str) -> str:
        """标准化文本格式"""
        # 统一换行符
        text = text.replace('\r\n', '\n').replace('\r', '\n')
        # 移除行尾空格
        lines = [line.rstrip() for line in text.split('\n')]
        return '\n'.join(lines)
    
    def _analyze_changes(self, diff_lines: List[str]) -> List[Dict[str, Any]]:
        """分析差异变更"""
        changes = []
        current_change = None
        
        for line in diff_lines:
            if line.startswith('@@'):
                # 新的变更块
                if current_change:
                    changes.append(current_change)
                
                # 解析行号信息
                match = re.search(r'@@ -(\d+)(?:,(\d+))? \+(\d+)(?:,(\d+))? @@', line)
                if match:
                    old_start, old_count, new_start, new_count = match.groups()
                    current_change = {
                        'old_start': int(old_start),
                        'old_count': int(old_count) if old_count else 1,
                        'new_start': int(new_start),
                        'new_count': int(new_count) if new_count else 1,
                        'added_lines': [],
                        'removed_lines': [],
                        'context_lines': []
                    }
            elif current_change:
                if line.startswith('+'):
                    current_change['added_lines'].append(line[1:])
                elif line.startswith('-'):
                    current_change['removed_lines'].append(line[1:])
                elif line.startswith(' '):
                    current_change['context_lines'].append(line[1:])
        
        if current_change:
            changes.append(current_change)
        
        return changes
    
    def _detect_semantic_conflicts(self, v1_changes: List[Dict], v2_changes: List[Dict], base_content: str) -> List[Dict[str, Any]]:
        """检测语义冲突"""
        conflicts = []
        base_lines = base_content.split('\n')
        
        for v1_change in v1_changes:
            for v2_change in v2_changes:
                # 检查是否有重叠的行范围
                v1_range = range(v1_change['old_start'], v1_change['old_start'] + v1_change['old_count'])
                v2_range = range(v2_change['old_start'], v2_change['old_start'] + v2_change['old_count'])
                
                overlap = set(v1_range).intersection(set(v2_range))
                if overlap:
                    # 计算冲突严重程度
                    severity = self._calculate_conflict_severity(v1_change, v2_change, base_lines)
                    
                    conflict = {
                        'v1_change': v1_change,
                        'v2_change': v2_change,
                        'overlapping_lines': list(overlap),
                        'severity': severity,
                        'base_content': '\n'.join(base_lines[min(overlap):max(overlap)+1])
                    }
                    conflicts.append(conflict)
        
        return conflicts
    
    def _calculate_conflict_severity(self, v1_change: Dict, v2_change: Dict, base_lines: List[str]) -> ConflictSeverity:
        """计算冲突严重程度"""
        # 简单的启发式规则
        v1_added = len(v1_change['added_lines'])
        v1_removed = len(v1_change['removed_lines'])
        v2_added = len(v2_change['added_lines'])
        v2_removed = len(v2_change['removed_lines'])
        
        total_changes = v1_added + v1_removed + v2_added + v2_removed
        
        if total_changes <= 2:
            return ConflictSeverity.LOW
        elif total_changes <= 5:
            return ConflictSeverity.MEDIUM
        else:
            return ConflictSeverity.HIGH
    
    def _apply_non_conflicting_changes(self, base_content: str, v1_changes: List[Dict], v2_changes: List[Dict]) -> str:
        """应用无冲突的变更"""
        lines = base_content.split('\n')
        
        # 按行号倒序应用变更（避免行号偏移问题）
        all_changes = [(change, 'v1') for change in v1_changes] + [(change, 'v2') for change in v2_changes]
        all_changes.sort(key=lambda x: x[0]['old_start'], reverse=True)
        
        for change, version in all_changes:
            start_line = change['old_start'] - 1  # 转换为0基索引
            end_line = start_line + change['old_count']
            
            # 替换行内容
            new_lines = change['added_lines']
            lines[start_line:end_line] = new_lines
        
        return '\n'.join(lines)
    
    def _resolve_conflicts_intelligently(self, base_content: str, v1_changes: List[Dict], v2_changes: List[Dict], conflicts: List[Dict]) -> MergeResult:
        """智能解决冲突"""
        resolved_conflicts = []
        unresolved_conflicts = []
        
        for conflict in conflicts:
            resolution = self._attempt_auto_resolution(conflict, base_content)
            if resolution['auto_resolved']:
                resolved_conflicts.append(resolution)
            else:
                unresolved_conflicts.append(conflict)
        
        # 应用自动解决的冲突
        merged_content = base_content
        confidence_scores = []
        
        for resolution in resolved_conflicts:
            merged_content = resolution['resolved_content']
            confidence_scores.append(resolution['confidence'])
        
        avg_confidence = sum(confidence_scores) / len(confidence_scores) if confidence_scores else 0.0
        
        return MergeResult(
            merged_content=merged_content,
            has_conflicts=len(unresolved_conflicts) > 0,
            conflicts=unresolved_conflicts,
            confidence_score=avg_confidence,
            auto_resolved=len(unresolved_conflicts) == 0
        )
    
    def _attempt_auto_resolution(self, conflict: Dict, base_content: str) -> Dict[str, Any]:
        """尝试自动解决冲突"""
        v1_change = conflict['v1_change']
        v2_change = conflict['v2_change']
        severity = conflict['severity']
        
        # 低严重程度的冲突尝试自动解决
        if severity == ConflictSeverity.LOW:
            return self._resolve_low_severity_conflict(conflict, base_content)
        
        # 中等严重程度的冲突使用启发式规则
        elif severity == ConflictSeverity.MEDIUM:
            return self._resolve_medium_severity_conflict(conflict, base_content)
        
        # 高严重程度的冲突需要人工解决
        else:
            return {
                'auto_resolved': False,
                'confidence': 0.0,
                'reason': 'High severity conflict requires manual resolution'
            }
    
    def _resolve_low_severity_conflict(self, conflict: Dict, base_content: str) -> Dict[str, Any]:
        """解决低严重程度冲突"""
        v1_change = conflict['v1_change']
        v2_change = conflict['v2_change']
        
        # 如果一个是添加，一个是修改，尝试合并
        if v1_change['added_lines'] and not v1_change['removed_lines']:
            # v1是纯添加
            if v2_change['removed_lines'] and v2_change['added_lines']:
                # v2是修改，可以将v1的添加合并到v2的修改中
                merged_lines = v2_change['added_lines'] + v1_change['added_lines']
                return {
                    'auto_resolved': True,
                    'resolved_content': '\n'.join(merged_lines),
                    'confidence': 0.7,
                    'strategy': 'append_addition_to_modification'
                }
        
        return {'auto_resolved': False, 'confidence': 0.0}
    
    def _resolve_medium_severity_conflict(self, conflict: Dict, base_content: str) -> Dict[str, Any]:
        """解决中等严重程度冲突"""
        v1_change = conflict['v1_change']
        v2_change = conflict['v2_change']
        
        # 使用文本相似度判断
        v1_text = '\n'.join(v1_change['added_lines'])
        v2_text = '\n'.join(v2_change['added_lines'])
        
        similarity = difflib.SequenceMatcher(None, v1_text, v2_text).ratio()
        
        if similarity > 0.8:
            # 高相似度，选择较长的版本
            if len(v1_text) > len(v2_text):
                return {
                    'auto_resolved': True,
                    'resolved_content': v1_text,
                    'confidence': similarity,
                    'strategy': 'choose_longer_similar_version'
                }
            else:
                return {
                    'auto_resolved': True,
                    'resolved_content': v2_text,
                    'confidence': similarity,
                    'strategy': 'choose_longer_similar_version'
                }
        
        return {'auto_resolved': False, 'confidence': similarity}

class RealTimeSync:
    """实时同步机制"""
    
    def __init__(self):
        self.active_editors: Dict[str, Dict[str, Any]] = {}
        self.operation_queue: List[Dict[str, Any]] = []
        self.sync_interval = 1.0  # 秒
    
    def register_editor(self, editor_id: str, session_info: Dict[str, Any]):
        """注册编辑器"""
        self.active_editors[editor_id] = {
            'session_info': session_info,
            'last_sync': time.time(),
            'pending_operations': []
        }
    
    def broadcast_operation(self, operation: Dict[str, Any], exclude_editor: str = None):
        """广播操作到其他编辑器"""
        for editor_id, editor_info in self.active_editors.items():
            if editor_id != exclude_editor:
                editor_info['pending_operations'].append(operation)
    
    def get_pending_operations(self, editor_id: str) -> List[Dict[str, Any]]:
        """获取待同步的操作"""
        if editor_id in self.active_editors:
            operations = self.active_editors[editor_id]['pending_operations'].copy()
            self.active_editors[editor_id]['pending_operations'].clear()
            self.active_editors[editor_id]['last_sync'] = time.time()
            return operations
        return []

class OperationalTransform:
    """操作变换 - 用于实时协作"""
    
    @staticmethod
    def transform_operations(op1: Dict[str, Any], op2: Dict[str, Any]) -> Tuple[Dict[str, Any], Dict[str, Any]]:
        """变换两个并发操作，使其可以安全应用"""
        
        # 简化的操作变换实现
        # 实际应用中需要更复杂的算法如OT或CRDT
        
        if op1['type'] == 'insert' and op2['type'] == 'insert':
            # 两个插入操作
            if op1['position'] <= op2['position']:
                # op1在前，op2位置需要后移
                op2_transformed = op2.copy()
                op2_transformed['position'] += len(op1['content'])
                return op1, op2_transformed
            else:
                # op2在前，op1位置需要后移
                op1_transformed = op1.copy()
                op1_transformed['position'] += len(op2['content'])
                return op1_transformed, op2
        
        elif op1['type'] == 'delete' and op2['type'] == 'delete':
            # 两个删除操作
            if op1['position'] < op2['position']:
                op2_transformed = op2.copy()
                op2_transformed['position'] -= op1['length']
                return op1, op2_transformed
            else:
                op1_transformed = op1.copy()
                op1_transformed['position'] -= op2['length']
                return op1_transformed, op2
        
        # 其他情况的变换逻辑...
        return op1, op2

class ConversationEditWorkflow:
    """对话编辑工作流"""
    
    def __init__(self):
        self.merge_engine = AdvancedMergeEngine()
        self.sync_manager = RealTimeSync()
        self.ot_engine = OperationalTransform()
        
    def create_edit_proposal(self, editor_id: str, message_id: str, proposed_content: str, current_version: str) -> Dict[str, Any]:
        """创建编辑提案"""
        proposal = {
            'proposal_id': str(uuid.uuid4()),
            'editor_id': editor_id,
            'message_id': message_id,
            'proposed_content': proposed_content,
            'base_version': current_version,
            'timestamp': time.time(),
            'status': 'pending',
            'reviews': []
        }
        return proposal
    
    def review_edit_proposal(self, proposal: Dict[str, Any], reviewer_id: str, approval: bool, comments: str = "") -> Dict[str, Any]:
        """审核编辑提案"""
        review = {
            'reviewer_id': reviewer_id,
            'approval': approval,
            'comments': comments,
            'timestamp': time.time()
        }
        proposal['reviews'].append(review)
        
        # 检查是否达到批准条件
        approvals = sum(1 for r in proposal['reviews'] if r['approval'])
        if approvals >= 1:  # 简化：一个批准即可
            proposal['status'] = 'approved'
        
        return proposal
    
    def apply_approved_proposal(self, proposal: Dict[str, Any], conversation_manager) -> bool:
        """应用已批准的编辑提案"""
        if proposal['status'] != 'approved':
            return False
        
        # 检查基础版本是否仍然有效
        current_main = conversation_manager.version_manager.main_version_id
        if proposal['base_version'] != current_main:
            # 需要重新基于最新版本
            return self._rebase_proposal(proposal, conversation_manager)
        
        # 直接应用编辑
        edit_op = EditOperation(
            id=proposal['proposal_id'],
            edit_type=EditType.MODIFY,
            target_message_id=proposal['message_id'],
            old_content=None,
            new_content=proposal['proposed_content'],
            position=None,
            timestamp=time.time(),
            editor_id=proposal['editor_id'],
            parent_version=proposal['base_version']
        )
        
        return conversation_manager.version_manager.apply_edit(proposal['editor_id'], edit_op)
    
    def _rebase_proposal(self, proposal: Dict[str, Any], conversation_manager) -> bool:
        """重新基于最新版本应用提案"""
        # 获取最新版本的消息内容
        current_messages = conversation_manager.get_conversation_history()
        current_message = next((msg for msg in current_messages if msg.id == proposal['message_id']), None)
        
        if not current_message:
            return False
        
        # 使用三路合并
        merge_result = self.merge_engine.intelligent_merge(
            base_content=proposal['base_version'],  # 这里需要获取实际的基础内容
            version1_content=current_message.content,
            version2_content=proposal['proposed_content']
        )
        
        if not merge_result.has_conflicts and merge_result.confidence_score > 0.8:
            # 自动合并成功
            edit_op = EditOperation(
                id=str(uuid.uuid4()),
                edit_type=EditType.MODIFY,
                target_message_id=proposal['message_id'],
                old_content=current_message.content,
                new_content=merge_result.merged_content,
                position=None,
                timestamp=time.time(),
                editor_id=proposal['editor_id'],
                parent_version=conversation_manager.version_manager.main_version_id
            )
            
            return conversation_manager.version_manager.apply_edit(proposal['editor_id'], edit_op)
        
        return False

# 使用示例
def demo_advanced_merge():
    """演示高级合并功能"""
    
    merge_engine = AdvancedMergeEngine()
    
    # 模拟三个版本的内容
    base_content = """你好，我是AI助手。
我可以帮助你解决各种问题。
请告诉我你需要什么帮助。"""
    
    version1_content = """你好，我是智能AI助手。
我可以帮助你解决各种技术问题。
请告诉我你需要什么帮助。"""
    
    version2_content = """你好，我是AI助手。
我可以帮助你解决各种问题和疑问。
请详细告诉我你需要什么帮助。"""
    
    # 执行智能合并
    result = merge_engine.intelligent_merge(base_content, version1_content, version2_content)
    
    print("=== 高级合并演示 ===")
    print(f"有冲突: {result.has_conflicts}")
    print(f"信心度: {result.confidence_score}")
    print(f"自动解决: {result.auto_resolved}")
    print(f"合并结果:\n{result.merged_content}")
    
    if result.conflicts:
        print("\n未解决的冲突:")
        for i, conflict in enumerate(result.conflicts):
            print(f"冲突 {i+1}: {conflict}")

if __name__ == "__main__":
    demo_advanced_merge()