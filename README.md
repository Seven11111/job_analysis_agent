<div align="center">

# 🧭 求职研究工作台

### Job Analysis Agent

<p>
  <a href="https://fastapi.tiangolo.com/"><img src="https://img.shields.io/badge/Backend-FastAPI-009688?logo=fastapi&logoColor=white" alt="Backend: FastAPI"></a>
  <a href="https://react.dev/"><img src="https://img.shields.io/badge/Frontend-React%2019-149ECA?logo=react&logoColor=white" alt="Frontend: React 19"></a>
  <a href="https://www.typescriptlang.org/"><img src="https://img.shields.io/badge/Language-TypeScript-3178C6?logo=typescript&logoColor=white" alt="Language: TypeScript"></a>
  <a href="https://www.sqlite.org/"><img src="https://img.shields.io/badge/Database-SQLite-003B57?logo=sqlite&logoColor=white" alt="Database: SQLite"></a>
</p>

面向个人求职过程的本地优先工作台：搜索和研究岗位，保存感兴趣的机会，结合个人简历分析匹配度，再由你决定后续行动。

[产品预览](#产品预览) · [功能特性](#功能特性) · [岗位来源与配置](#岗位来源与配置) · [快速开始](#快速开始) · [项目文档](#项目文档)

</div>

> 不自动投递，不绕过招聘网站的登录、验证码或访问限制。搜索结果先临时展示，只有用户确认后才会保存。

## 🖥️ 产品预览

以下是页面设计示意图；岗位、公司和日期均为演示内容，不代表当前真实搜索结果。

<p align="center">
  <img src="docs/assets/workbench.png" alt="求职研究工作台首页示意" width="900">
</p>

<table>
  <tr>
    <td align="center" width="50%">
      <img src="docs/assets/job-search.png" alt="岗位搜索页面示意" width="100%"><br>
      <sub>岗位搜索 · 条件筛选与来源信息</sub>
    </td>
    <td align="center" width="50%">
      <img src="docs/assets/job-management.png" alt="岗位管理页面示意" width="100%"><br>
      <sub>岗位管理 · 状态跟踪与匹配分析</sub>
    </td>
  </tr>
  <tr>
    <td align="center" width="50%">
      <img src="docs/assets/profile.png" alt="个人画像页面示意" width="100%"><br>
      <sub>个人画像 · 求职偏好、技能、项目与简历</sub>
    </td>
    <td align="center" width="50%">
      <img src="docs/assets/agent.png" alt="求职 Agent 页面示意" width="100%"><br>
      <sub>求职 Agent · 多轮对话与岗位工具</sub>
    </td>
  </tr>
</table>

## ✨ 功能特性

| 能力 | 说明 |
| --- | --- |
| 实习岗位搜索 | 通过已配置的 job-pro、BOSS 等来源按关键词、公司、城市和日期查找岗位；每个来源独立显示状态，结果不会自动入库。 |
| 校招资讯 | 通过 Offer 先生官方 API 查询招聘公告、届别、招聘批次、城市和网申信息；这是独立的资讯来源，不等同于实习岗位搜索。 |
| 岗位管理 | 人工保存岗位，自定义状态、状态时间和备注；查看原始信息与匹配分析。 |
| 岗位匹配分析 | 使用 LiteLLM 配置的模型，结合岗位要求和个人简历生成结构化匹配结果。 |
| 个人画像与简历 | 维护在线简历和求职偏好；上传附件简历后解析，并在确认后用于分析。 |
| 求职 Agent | 连续对话，并通过工具查询或管理已保存岗位、求职进度和个人画像。 |
| 本地优先 | 面向单用户本地运行；数据库、配置和上传文件保存在本机。Fixture 可离线验证基础流程，但不提供真实岗位数据。 |

## 🔌 岗位来源与配置

### 真实岗位搜索必须启用来源

如果要搜索真实的实习岗位，必须至少配置并启用一个可用来源：**job-pro 或 BOSS 直聘**。不配置真实来源时，应用仍可用离线 Fixture 启动，但只能用于流程演示，不能当作真实搜索结果。

| 来源 | 用途 | 使用前需要做什么 |
| --- | --- | --- |
| [job-pro](https://github.com/HA7CH/job-pro) | 公开招聘接口聚合搜索，当前项目将范围限定为实习，并可配置公司来源 ID。 | 安装项目适配的 CLI；在 `JOB_PRO_COMPANIES` 设置要搜索的公司 ID。 |
| BOSS 直聘（`boss-agent-cli`） | 使用本机的官方登录态进行只读岗位搜索。 | 安装 CLI，并在项目专用浏览器中完成官方登录；项目不采集密码、短信验证码或 Cookie。 |
| [Offer 先生](https://developer.offerxiansheng.com/docs/ai/guides) | 独立的校园招聘资讯公告搜索，不属于实习岗位 `JobRecord` 搜索来源。 | 配置 `OFFER_XIANSHENG_API`。可在[官方 API Keys 页面](https://developer.offerxiansheng.com/account/api-keys)创建密钥。 |
| Fixture | 离线开发和测试数据。 | 无需配置；不属于真实岗位来源。 |

job-pro 与 BOSS 用于实习岗位搜索；Offer 先生对应单独的“校招资讯”功能。**只配置 Offer 先生并不能满足真实实习岗位搜索的来源要求。**

### 配置示例

复制 `.env.example` 为 `.env`，然后按要使用的能力填写。下面展示的是配置项名称和占位值，不要将真实密钥提交到仓库：

```dotenv
# 实时实习岗位搜索至少启用 job-pro 或 boss_agent_cli，可同时使用多个。
JOB_PROVIDER=job_pro
JOB_PRO_COMPANIES=bytedance,tencent,alibaba,xiaohongshu

# 使用 BOSS 时安装 CLI 并完成官方登录；不使用时无需配置 BOSS。
BOSS_CLI_COMMAND=./.tools/bin/boss

# 使用 Offer 先生校招资讯时单独填写 API Key，不替代上面的实习岗位来源。
OFFER_XIANSHENG_API=<your-offer-xiansheng-api-key>

# 岗位深度分析、简历解析和求职 Agent 需要模型配置；OpenAI 兼容服务示例。
LITELLM_PROVIDER=openai
LITELLM_MODEL=<provider-model-id>
OPENAI_API_KEY=<your-model-api-key>
OPENAI_BASE_URL=<openai-compatible-api-base-url>
```

| 配置项 | 用途 |
| --- | --- |
| `JOB_PROVIDER` | 后端未收到显式来源时的默认值，可设 `job_pro`、`boss_agent_cli` 或逗号分隔的多个来源；`fixture` 仅用于离线演示。前端搜索时用户选择的来源优先。 |
| `JOB_PRO_COMPANIES` | job-pro 公司来源 ID 白名单，以英文逗号分隔；具体可用范围受 job-pro 支持情况限制。 |
| `BOSS_CLI_COMMAND` | BOSS CLI 可执行文件位置；使用安装脚本时默认是 `./.tools/bin/boss`。 |
| `OFFER_XIANSHENG_API` | Offer 先生校招资讯 API Key；只在使用该独立资讯功能时需要。 |
| `LITELLM_PROVIDER`、`LITELLM_MODEL` | 指定 LiteLLM 路由 Provider 与模型 ID；用于岗位分析、简历解析和求职 Agent，不是运行岗位搜索的前置条件。 |
| `OPENAI_API_KEY`、`OPENAI_BASE_URL` | OpenAI 兼容模型服务的认证密钥和 API 根地址；其他原生 Provider 可能需要各自的认证变量。 |
| `DATABASE_PATH` | SQLite 数据库文件位置；默认 `./data/job_analysis.db`。 |

完整字段说明、LiteLLM Provider 示例、浏览器登录配置、依赖目录与常见问题见[环境变量与依赖配置指南](docs/configuration.md)。

## 🚀 快速开始

### 1. 安装项目依赖

```bash
python -m venv .venv
.venv/bin/pip install -r requirements.txt
cp .env.example .env
```

编辑 `.env` 并为真实实习岗位搜索至少启用 job-pro 或 BOSS。只运行离线演示时可保留 `JOB_PROVIDER=fixture`。如需岗位深度分析、简历解析或 Agent，再配置可用的 LiteLLM 模型。

### 2. 安装所需岗位来源

安装脚本将 CLI 放入项目忽略目录 `.tools/`，不污染全局 Python/npm 环境。需要 `uv`、Node.js 18+ 和 npm：

```bash
# 安装 job-pro 和 BOSS
bash scripts/install_provider_tools.sh all

# 或只安装要使用的来源
bash scripts/install_provider_tools.sh job-pro
bash scripts/install_provider_tools.sh boss
```

BOSS 还需在项目专用浏览器中完成官方登录。安装后可查看健康检查确认来源状态。

### 3. 启动后端

```bash
.venv/bin/alembic upgrade head
.venv/bin/uvicorn server:app --reload --host 127.0.0.1 --port 8100
```

### 4. 启动前端

另开一个终端，先进入求职项目根目录：

```bash
cd apps/web
npm install
npm run dev
```

- Web 页面：<http://127.0.0.1:5173>
- Swagger API 文档：<http://127.0.0.1:8100/docs>
- 健康检查与来源状态：<http://127.0.0.1:8100/api/v1/health>

## 📚 项目文档

- [产品需求 PRD](docs/PRD.md)
- [实施计划](docs/IMPLEMENTATION_PLAN.md)
- [技术架构](docs/design/architecture.md)
- [数据模型](docs/design/data-model.md)
- [API 契约](docs/design/api-contract.md)
- [环境变量、来源配置与依赖安装指南](docs/configuration.md)
