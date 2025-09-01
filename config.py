"""
系统配置文件
"""

# 版本控制配置
VERSION_CONFIG = {
    "max_versions": 100,           # 最大保留版本数
    "auto_cleanup_interval": 3600, # 自动清理间隔（秒）
    "session_timeout": 1800,       # 编辑会话超时时间（秒）
}

# 合并策略配置
MERGE_CONFIG = {
    "default_strategy": "auto",     # 默认合并策略
    "auto_merge_threshold": 0.8,   # 自动合并信心度阈值
    "conflict_resolution_timeout": 300,  # 冲突解决超时时间（秒）
    "enable_smart_merge": True,     # 启用智能合并
    "preserve_formatting": True,    # 保持格式
}

# 实时协作配置
COLLABORATION_CONFIG = {
    "websocket_host": "localhost",
    "websocket_port": 8765,
    "max_concurrent_editors": 10,  # 最大并发编辑者数量
    "operation_queue_size": 1000,  # 操作队列大小
    "sync_interval": 0.5,          # 同步间隔（秒）
    "enable_conflict_prevention": True,  # 启用冲突预防
}

# 备份配置
BACKUP_CONFIG = {
    "auto_backup_interval": 300,   # 自动备份间隔（秒）
    "max_backups": 50,             # 最大备份数量
    "backup_on_major_edit": True,  # 重大编辑时自动备份
}

# 日志配置
LOGGING_CONFIG = {
    "log_level": "INFO",
    "log_file": "conversation_editor.log",
    "log_operations": True,        # 记录所有操作
    "log_conflicts": True,         # 记录冲突信息
}