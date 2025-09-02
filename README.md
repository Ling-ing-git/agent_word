# OpenAI 多配置管理器

基于 OpenAI 库的多配置模型调用管理系统，支持多个 API 配置、模型调用、验证和随机调用功能。

## 功能特点

- 📋 **JSON 配置管理**: 支持单个配置对象或配置数组
- 🔄 **智能重试机制**: 支持最多 3 次自动重试，采用指数退避策略
- ✅ **配置验证**: 自动验证 API 配置的有效性
- 🎲 **随机调用**: 支持在指定范围内随机选择配置进行调用
- 🛡️ **错误处理**: 完善的异常处理和错误提示

## 安装依赖

```bash
pip install -r requirements.txt
```

## 配置文件格式

创建 `config.json` 文件，支持以下两种格式：

### 单个配置对象
```json
{
    "url": "https://api.openai.com/v1",
    "model": "gpt-3.5-turbo",
    "apikey": "your-api-key"
}
```

### 多个配置数组
```json
[
    {
        "url": "https://api.openai.com/v1",
        "model": "gpt-3.5-turbo",
        "apikey": "your-openai-api-key-1"
    },
    {
        "url": "https://api.openai.com/v1",
        "model": "gpt-4",
        "apikey": "your-openai-api-key-2"
    },
    {
        "url": "https://your-custom-endpoint.com/v1",
        "model": "custom-model",
        "apikey": "your-custom-api-key"
    }
]
```

## 使用方法

### 基本用法

```python
from openai_manager import OpenAIManager

# 初始化管理器
manager = OpenAIManager("config.json")

# 准备对话消息
messages = [
    {"role": "user", "content": "你好，请介绍一下人工智能"}
]
```

### 1. 模型调用 (`call_model`)

```python
# 使用指定配置（第0个配置）调用模型
response = manager.call_model(
    config_index=0,  # 指定配置项索引
    messages=messages,  # 标准对话记录数组
    max_tokens=100,  # 可选参数
    temperature=0.7  # 可选参数
)

print(response["choices"][0]["message"]["content"])
```

**特点:**
- 直接返回原始 OpenAI API 响应
- 支持最多 3 次自动重试
- 采用指数退避重试策略
- 支持所有 OpenAI API 参数

### 2. 模型验证 (`validate_model`)

```python
# 验证指定配置是否有效
is_valid = manager.validate_model(config_index=0)
print(f"配置0是否有效: {is_valid}")

# 验证所有配置
results = manager.validate_all_configs()
for config_idx, is_valid in results.items():
    print(f"配置 {config_idx}: {'有效' if is_valid else '无效'}")
```

**特点:**
- 自动发送测试消息 `[{"role": "user", "content": "你好"}]`
- 限制返回字数为 10 个字，节省资源
- 返回 True/False 验证结果

### 3. 随机调用 (`random_call`)

```python
# 在所有配置中随机选择
response = manager.random_call(
    messages=messages,
    max_tokens=100
)

# 在指定范围内随机选择（只在配置0和1中选择）
response = manager.random_call(
    messages=messages,
    config_range=[0, 1],  # 指定配置范围
    max_tokens=100
)
```

**特点:**
- 支持指定配置范围，默认使用全部配置
- 自动过滤无效的配置索引
- 返回原始 OpenAI API 响应

### 其他实用功能

```python
# 获取配置信息（隐藏 API 密钥）
configs = manager.get_config_info()
for config in configs:
    print(f"配置 {config['index']}: {config['model']} @ {config['url']}")
```

## 运行示例

```bash
python example_usage.py
```

## 错误处理

系统提供完善的错误处理：

- **配置文件错误**: 文件不存在或 JSON 格式错误
- **配置索引错误**: 超出有效范围的配置索引
- **API 调用错误**: 网络错误、认证失败等
- **重试机制**: 自动重试失败的请求，最多 3 次

## 配置项说明

| 字段 | 说明 | 示例 |
|------|------|------|
| `url` | API 端点地址 | `https://api.openai.com/v1` |
| `model` | 模型名称 | `gpt-3.5-turbo`, `gpt-4` |
| `apikey` | API 密钥 | `sk-...` |

## 注意事项

1. 请确保 API 密钥的安全性，不要将其提交到版本控制系统
2. 配置索引从 0 开始计数
3. 验证功能会消耗少量 API 配额
4. 重试机制采用指数退避，避免过度请求

## 许可证

MIT License