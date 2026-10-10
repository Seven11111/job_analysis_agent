# Job Analysis Agent 协作规则

本项目是独立的本地单用户岗位研究 Agent，技术和业务约束以 `docs/` 下文档为准。

## 目录边界

- `api/`：FastAPI 路由、依赖和响应契约。
- `src/`：业务、数据库、Provider、LLM 和记忆模块。
- `apps/web/`：React 前端。
- `migrations/`：Alembic 迁移。
- `tests/`：离线测试和网络标记测试。
- `docs/`：PRD、架构、数据模型、API 契约和原型图。

## 开发规则

- 不自动投递岗位，不绕过招聘网站登录、验证码或反爬机制。
- 不把手机号、邮箱、身份证和详细住址发送给 LLM。
- 岗位状态只能由用户修改；状态修改必须写入状态历史。
- 岗位匹配必须由用户主动触发，模型输出必须经过结构化校验。
- Provider、LLM 和数据库配置只从本项目自己的 `.env` 读取。
- 数据库变更使用 Alembic，不在应用启动时静默建表。
- 优先使用 Fixture 完成离线开发，普通测试不得依赖网络。
- 未经明确要求不执行 commit、push 或删除用户数据。

## 常用命令

```bash
python -m venv .venv
.venv/bin/pip install -r requirements.txt
.venv/bin/alembic upgrade head
.venv/bin/python main.py --help
.venv/bin/uvicorn server:app --reload --port 8100

# 可选：把 BOSS CLI 与 job-pro 安装到项目内 .tools/，不使用全局 CLI
bash scripts/install_provider_tools.sh all

cd apps/web
npm install
npm run dev
```
