# 环境变量与依赖配置

求职项目只读取项目根目录下的 `.env`。新环境从 `.env.example` 复制一份后再填配置；`.env`、API Key、简历和数据库均为本机数据，不应提交到公开仓库。

```bash
cp .env.example .env
```

如果 `.env` 已存在，不要再次复制覆盖；只按下文修改需要的字段。修改环境变量后需重启后端。

## 真实岗位来源要求

应用可以在不配置真实来源时以 Fixture 离线启动，但 Fixture 只用于流程演示和测试，不会提供实时岗位。要进行真实的实习岗位搜索，必须至少启用一个可用来源：`job_pro` 或 `boss_agent_cli`。Offer 先生提供的是独立的校招资讯公告搜索，不属于实习岗位 `JobRecord` 来源，不能替代上述实习岗位来源。

每个来源单独配置即可：job-pro 需要安装本地 CLI；BOSS 需要安装 CLI 并由用户完成官方登录；Offer 先生需要单独配置官方 API Key。无需使用某来源时不必配置该来源的凭据。

## 配置分组

### 本地项目配置

- `DATABASE_PATH`：SQLite 数据库文件。相对路径以项目根目录为基准，默认保存到 `data/job_analysis.db`。
- `JOB_PROVIDER`：请求没有显式指定来源时使用的默认来源；`fixture` 仅用于离线开发。前端主动提交的来源优先。
- `IMPORT_TIMEOUT_SECONDS`：读取公开岗位链接的时间上限，包含 JavaScript 页面渲染等待。
- `CORS_ORIGINS`：允许访问 API 的前端地址，多个 origin 用英文逗号分隔；默认包含 Vite 开发端口 `5175`（并兼容 `5173`）。
- `LOG_LEVEL`：日志级别，例如 `INFO`、`WARNING`、`DEBUG`。

### BOSS 直聘 CLI

实习岗位只读搜索来源之一。若希望搜索 BOSS，安装需要本机有 `uv`；执行：

```bash
bash scripts/install_provider_tools.sh boss
```

默认安装位置如下，均被 `.gitignore` 排除：

- CLI 独立 Python 工具环境：`.tools/uv/`
- 可执行命令：`.tools/bin/boss`
- `BOSS_CLI_COMMAND=./.tools/bin/boss`：告诉后端运行哪个 BOSS 命令。带路径的配置按项目根目录解析，不依赖全局 `PATH`；也可改成绝对路径或 `PATH` 命令名。
- `BOSS_CLI_TIMEOUT_SECONDS`、`BOSS_LOGIN_TIMEOUT_SECONDS`：搜索和登录等待上限，单位秒。
- `BOSS_BROWSER_SOURCE`、`BOSS_CDP_URL`：使用本地可见浏览器及其 CDP 地址。默认 CDP 地址为 `http://127.0.0.1:9222`。
- `BOSS_CHROME_PATH`：可选的 Chrome/Chromium 可执行文件路径；留空时由 CLI/系统发现。
- `BOSS_CHROME_PROFILE_PATH`：项目专用浏览器用户数据目录，用来保留官方登录状态。不要指向个人日常 Chrome 用户目录，也不要将该目录提交到仓库。
- `BOSS_AUTO_START_CHROME`：是否由项目启动专用浏览器。
- `BOSS_RISK_COOLDOWN_SECONDS`：触发 BOSS 风控后的冷却期；该设置不会规避风控。

登录须由用户在官方页面完成。本项目不收集密码、短信验证码或 Cookie，不自动投递，不尝试绕过登录或访问限制。

### job-pro CLI

公开招聘接口聚合来源之一。若希望搜索 job-pro，安装需要 Node.js 18+ 和 npm：

```bash
bash scripts/install_provider_tools.sh job-pro
```

CLI 安装在 `.tools/job-pro/`，可执行入口为 `.tools/job-pro/node_modules/.bin/job-pro`。`JOB_PRO_COMMAND` 默认指向该入口；相对路径同样以项目根目录解析。可通过 `JOB_PRO_TIMEOUT_SECONDS` 调整等待上限，`JOB_PRO_SCOPE=intern` 将搜索范围限定为实习岗位，`JOB_PRO_COMPANIES` 用英文逗号分隔公司来源 ID。当前锁定的 `@ha7ch/job-pro@1.2.1` 声明支持 50 家公司；项目默认启用这 50 家，也可以在 `.env` 中删减。运行 `job-pro list` 可查看固定版本的公司 ID 和来源类型。来源接入不代表每家公司每次都能返回结果；招聘接口状态和实习岗位数据由上游决定，其中 job-pro 标注的 Liepin 第三方回退来源也可能有不同的可用性。

脚本固定安装项目当前适配的 `@ha7ch/job-pro@1.2.1`。如单独通过全局 npm 安装，也可将 `JOB_PRO_COMMAND` 改成 `job-pro`；但为了可复现和减少机器差异，推荐使用项目内安装。

### Offer 先生校招资讯 API

独立的官方校招资讯公告来源，不属于实习岗位搜索 Provider。若要使用校招资讯页面，前往 [Offer 先生 API Keys 页面](https://developer.offerxiansheng.com/account/api-keys) 创建 Key，将其仅填入后端 `.env` 的 `OFFER_XIANSHENG_API`。API 接入说明见[官方指南](https://developer.offerxiansheng.com/docs/ai/guides)。

`OFFER_XIANSHENG_TIMEOUT_SECONDS` 控制请求超时。密钥不会发送给前端，也不应写进 README、截图、日志或提交记录。

### LiteLLM 模型路由

LiteLLM 用于岗位深度分析、简历解析和求职 Agent。`LITELLM_PROVIDER` 是路由前缀/Provider 名，`LITELLM_MODEL` 是模型 ID；项目会在模型 ID 缺少当前前缀时自动补上。

推荐：如果模型服务兼容 OpenAI Chat Completions API（自建服务或第三方兼容 API），配置为：

```dotenv
LITELLM_PROVIDER=openai
LITELLM_MODEL=<服务商提供的模型 ID>
OPENAI_API_KEY=<服务商 API Key>
OPENAI_BASE_URL=<兼容 API 根地址，通常以 /v1 结尾>
```

例如，中国科技云的兼容地址可填在 `OPENAI_BASE_URL`，而 `LITELLM_MODEL` 填控制台给出的模型 ID。这里的 `openai` 表示 API 协议/路由，不代表密钥必须来自 OpenAI。

LiteLLM 还支持许多原生 Provider，例如 `openrouter`、`anthropic`、`gemini`、`deepseek`、`ollama`、`azure`、`bedrock`、`vertex_ai` 等。可选值、模型 ID 格式及额外认证要求会随 LiteLLM 版本变化，请以[官方 Provider 文档](https://docs.litellm.ai/docs/providers)为准。对于需要额外 Provider 专属凭据的原生路由，应按 LiteLLM 文档在启动后端的 shell 环境中配置对应变量；项目当前 `.env` 中的统一凭据入口是 `OPENAI_API_KEY` 和 `OPENAI_BASE_URL`，不代表所有云 Provider 都只需要这两项。

- `OPENAI_API_KEY`：显式传给 LiteLLM 调用的 API Key。不要提交真实值。
- `OPENAI_BASE_URL`：自定义兼容接口的根 URL；如果用 Provider 原生默认地址，可留空。
- `LLM_TEMPERATURE`：生成随机度，通常为 `0` 到 `1` 之间。
- `LLM_TIMEOUT_SECONDS`：模型请求超时上限。

## 依赖放置位置

| 依赖 | 安装/下载位置 | 说明 |
| --- | --- | --- |
| Python 包 | `.venv/` | `pip install -r requirements.txt`，与系统 Python 隔离。 |
| BOSS CLI | `.tools/uv/`、`.tools/bin/` | 使用项目脚本和 `UV_TOOL_DIR` / `UV_TOOL_BIN_DIR` 固定目录。 |
| job-pro CLI | `.tools/job-pro/` | 用 npm `--prefix` 安装到项目目录，不需要全局 npm 包。 |
| 前端 npm 包 | `apps/web/node_modules/` | 在 `apps/web` 运行 `npm install`。 |
| Playwright 浏览器 | 默认系统用户缓存 | macOS 默认 `~/Library/Caches/ms-playwright`；可通过 `PLAYWRIGHT_BROWSERS_PATH` 指定自定义目录。 |

Playwright 浏览器二进制需要单独安装，且版本需匹配项目的 Playwright Python 包：

```bash
.venv/bin/python -m playwright install chromium
```

若希望将其放在项目的忽略目录中，安装与运行时必须使用同一个目录变量，例如：

```bash
PLAYWRIGHT_BROWSERS_PATH="$PWD/.tools/playwright" .venv/bin/python -m playwright install chromium
PLAYWRIGHT_BROWSERS_PATH="$PWD/.tools/playwright" .venv/bin/uvicorn server:app --host 127.0.0.1 --port 8100
```

不设置该变量时，Playwright 使用操作系统的用户缓存目录；安装命令与后端运行命令应保持一致。`.tools/`、`.venv/`、`node_modules/` 和 `.env` 均不应纳入 Git。
