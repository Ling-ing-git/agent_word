# AI 女友（最小可运行版本）

- 后端：FastAPI
- 前端：静态页面（内置）
- 对话引擎：优先 OpenAI（可选），无 Key 则使用本地轻量规则回复

## 本地运行

1. 创建并激活虚拟环境（可选）
2. 安装依赖：
   ```bash
   pip install -r ai_girlfriend/requirements.txt
   ```
3. 启动服务：
   ```bash
   uvicorn ai_girlfriend.app.main:app --host 0.0.0.0 --port 8000 --reload
   ```
4. 打开浏览器访问：`http://localhost:8000`

## OpenAI（可选）
- 复制 `ai_girlfriend/.env.example` 为 `.env` 并写入 `OPENAI_API_KEY`
- 默认模型：`gpt-4o-mini`，可通过 `OPENAI_MODEL` 覆盖

## 结构
- `ai_girlfriend/app`：后端代码
- `ai_girlfriend/static`：前端静态资源
- `ai_girlfriend/personas`：人格配置
- `ai_girlfriend/data/sessions`：会话数据（JSON）