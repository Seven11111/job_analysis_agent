# Job Analysis Agent 技术架构

本文档约束项目的技术选型、代码分层和核心运行流程。产品范围、页面目标和验收标准见 [PRD.md](../PRD.md)；数据库字段和关系见 [data-model.md](data-model.md)；接口请求响应见 [api-contract.md](api-contract.md)。

## 1. 技术选型

### 后端

```text
Python
FastAPI
Pydantic
SQLAlchemy 2.x
Alembic
SQLite
LiteLLM
Playwright（按需渲染公开 JS 页面）
pytest
```

- FastAPI：HTTP API、OpenAPI 文档和 SSE 响应。
- Pydantic：请求、响应、结构化匹配结果和 Agent 事件校验。
- SQLAlchemy：ORM 和 Repository 数据访问。
- Alembic：数据库迁移，禁止使用启动时自动建表替代迁移。
- SQLite：本地单用户数据库，JSON 统一使用 TEXT 序列化保存。
- LiteLLM：统一不同模型服务商，Provider、模型名、Base URL 和密钥全部来自配置。`LITELLM_PROVIDER` 是 LiteLLM 的路由类型；OpenAI 兼容的第三方服务（如中国科技云）使用 `openai`，服务地址仍由 `OPENAI_BASE_URL` 指向。
- Playwright：仅在公开页面的静态 HTML 是 JS 外壳或静态 HTTP 遇到网络传输错误时，使用普通无头浏览器读取渲染后的可见正文；打开页面后在现有导入超时预算内等待岗位职责/要求等正文信号，而不是按固定短延迟读取。XHR/fetch POST 仅用于 HTTPS 岗位详情只读请求：要求同源或可确认的同站点、岗位相关 API 路径、请求参数包含岗位 ID 且请求体不超过 64 KB；登录/投递/提交等写操作、跨站点或无法确认站点边界的请求仍拦截。浏览器使用全新上下文，不复用用户登录态。HTTP 401/403/429 等拒绝或限流响应不会重试。不登录、不处理验证码、不绕过风控或访问限制。页面正文由 LLM 依照证据约束抽取，提取失败时不生成成功预览。

### 前端

```text
React
TypeScript
Vite
Axios
React Router
Zustand
Tailwind CSS
Lucide React
React Markdown + remark-gfm
@microsoft/fetch-event-source
Vitest + React Testing Library
ESLint + Prettier
```

约束：

- Node.js 使用 LTS 版本，包管理器统一使用 npm。
- REST 请求统一经过 Axios 实例；Agent POST SSE 统一使用 `@microsoft/fetch-event-source`。
- Zustand 只保存跨页面状态，表单临时状态留在页面组件内部。
- Tailwind CSS 是唯一的样式方案，Lucide React 是唯一的图标库。
- 岗位匹配结果使用结构化 JSON 渲染；Markdown 只用于 Agent 的说明性回答。
- 第一版不引入大型 UI 组件库、复杂图表库和向量检索组件。

## 2. 项目分层

```text
job_analysis_agent/
├── api/                 # HTTP 接口、依赖和 OpenAPI 契约
├── src/
│   ├── config.py        # 环境变量和运行配置
│   ├── db/              # Base、Session、ORM Models
│   ├── repositories/    # 数据库读写
│   ├── data_provider/   # 合规岗位来源适配
│   ├── services/        # 岗位、画像、状态、匹配业务
│   ├── core/            # 搜索和匹配流程编排
│   ├── llm/             # LiteLLM、Prompt、结构化解析
│   ├── memory/          # 画像事实的召回、确认和替代
│   └── schemas/         # 内部领域 Schema
├── apps/web/            # React 前端
├── migrations/          # Alembic 迁移
├── data/                # SQLite 和本地 Fixture
└── tests/               # 离线测试和网络标记测试
```

依赖方向固定为：

```text
api → services/core → repositories/data_provider/llm
services → schemas
repositories → db
apps/web → api
```

API 层不能直接访问 ORM；Provider 不能直接写数据库；LLM 不能直接修改长期画像或岗位状态。

## 3. Provider 架构

统一接口由 `JobProvider` 定义，第一版实现：

```text
JobProvider
├── FixtureProvider
├── JobProProvider
├── BossAgentProvider
├── ManualImportProvider
└── ShixisengProvider

CampusRecruitProvider（独立公告域，不实现 JobProvider）
└── OfferXianshengProvider
```

- FixtureProvider：离线开发和测试，始终可用。
- ManualImportProvider：用户主动提供公开岗位链接，按通用流程读取不同招聘网站的 JSON-LD、静态 HTML 和可见正文；静态内容不足时按需用普通 Playwright 渲染，并在导入超时预算内等待岗位正文。XHR/fetch POST 仅用于 HTTPS 岗位详情只读请求：要求同源或可确认的同站点、岗位相关 API 路径、请求参数包含岗位 ID 且请求体不超过 64 KB；登录/投递/提交等写操作、跨站点或无法确认站点边界的请求仍拦截。再由 LLM 从已读取正文抽取结构化字段。只有预览不会写库，人工确认后才持久化；不登录、不复用用户登录态、不绕过验证码、反爬或访问限制。对于必须登录、验证码或拒绝公开读取的页面，返回来源限制提示，不声称已读取。
- ShixisengProvider：具备官方授权凭据时启用。
- OfferXianshengProvider：使用服务端 `OFFER_XIANSHENG_API` 调用官方校招搜索 API，标准化为独立校招公告数据；采用官方游标分页，只读且不写入实习岗位表。API Key 不返回前端，不写入日志。

Provider 只负责获取和标准化来源数据，不负责收藏、状态、匹配或记忆。单个 Provider 失败时保留其他 Provider 的结果，并在响应中返回来源状态和失败原因。

Offer 先生的数据是公告级记录而非具体实习岗位，因此不并入 `JobProvider` 的 `JobRecord` 契约；`date` 表示届别年份，`recruitPosInfoNameList` 是职位分类而非岗位标题。富文本只提取纯文本后展示，不将不可信 HTML 渲染到浏览器。

## 4. 核心业务流程

### 4.1 岗位搜索

```text
用户输入条件
→ 选择性召回长期画像
→ Provider 搜索
→ 标准化岗位
→ 来源岗位去重
→ 按 published_date、城市、实习条件和薪资状态规则筛选
→ 写入 jobs / job_snapshots
→ 返回岗位列表和来源质量摘要
```

搜索结果不会自动成为收藏，也不会自动触发 LLM 分析。

Offer 先生校招资讯走独立的 `POST /campus-recruit/search`：按官方 `nextCursor` 请求单页并返回 `has_more`，前端只提供上一页/下一页，不声称知道总数或支持任意跳页。结果保留在响应和浏览器状态中，不持久化到 SQLite，不调用岗位匹配服务。

### 4.2 收藏和岗位管理

```text
用户点击收藏
→ 创建 applications
→ 使用默认或用户自定义状态
→ 岗位出现在岗位管理页
→ 用户修改状态、时间和备注
→ 写入 application_status_events
```

岗位不会物理删除，只更新生命周期或收藏关系。

### 4.3 岗位匹配分析

```text
用户在岗位管理页点击分析
→ 读取岗位最新快照
→ 读取当前画像和用户选择的简历版本
→ 规则结果作为 Prompt 事实
→ LiteLLM 生成结构化报告
→ Pydantic 校验
→ 保存 job_matches
```

LLM 失败时不创建成功匹配记录；未公开薪资、缺失发布日期和 Provider 失败必须在数据质量中明确标注，禁止模型猜测。

### 4.4 附件简历解析

```text
用户主动上传 PDF/DOCX 并勾选模型处理同意
→ 服务端校验格式、文件大小和文档结构
→ 本机提取姓名、手机号和邮箱，并从模型输入中移除
→ 本机提取可读文本，对身份证和详细住址等信息脱敏
→ LiteLLM 生成 Pydantic 校验的结构化草稿
→ 将本机提取的基本联系信息合并回草稿
→ 保存原始附件和待确认草稿
→ 用户检查、编辑并确认
→ 新建 resume_versions 并关联 source_attachment_id
```

解析结果只作为草稿，不自动改写求职偏好、画像事实或当前简历。附件正文在用户明确同意前不会发送给模型；原始文件只存本地，模型调用只接收移除姓名/联系方式并脱敏后的提取文本。在线简历以版本化 JSON 保存基本信息、求职意向、教育、校园、工作/实习、项目和技能等区块。用户删除附件时只删除源文件和附件记录，已确认在线简历和历史分析保留。

### 4.5 求职 Agent

```text
用户问题
→ 保存用户消息并载入有限长度的会话历史
→ LiteLLM 原生 Tool Calling 判断并调用已注册工具
→ 读取实时 Provider、收藏岗位、状态时间、画像、简历或匹配分析
→ 对任何写操作生成持久化的待确认提案
→ SSE 推送运行事件、回答增量和最终答复
```

第一版支持岗位搜索、收藏岗位/状态/时间线查询、投递状态汇总、岗位比较、岗位匹配分析、个人画像和当前简历查询、通用对话，以及岗位、画像和简历的待确认修改。会话、用户/助手消息和运行事件持久化在 SQLite；会话标题可改名，用户可切换历史会话继续对话。

岗位搜索结果仍是临时结果，不会因 Agent 搜索自动写入岗位库；用户明确要求收藏时先生成提案，确认后才保存。岗位状态、备注、画像字段、简历结构化区块的修改，以及移除收藏关系，都必须通过 `action_proposed` 事件和确认接口执行。简历修改另存为新当前版本，姓名和联系方式只从本机现有简历保留，不经 LLM 往返。删除只移除个人岗位跟踪关系，不删除来源岗位、快照和匹配历史。

待确认操作会在会话刷新后继续展示；会话详情返回最近 200 条事件并补入所有尚未处理的操作。`action_proposed` 发出后，当前 SSE 运行暂停在该节点；用户确认或取消后，后端将执行结果作为工具结果交还模型并继续当前回答。待处理期间，前端暂停输入和发送，后端也以 `409 pending_action_confirmation` 拒绝同一会话的新消息；确认后若当前回答仍在生成，以 `409 run_in_progress` 防止并发。若 SSE 运行已中断，用户处理操作后可主动发送下一条消息继续；被拒绝的请求不会自动重发。

普通对话不强制调用工具。凡涉及岗位、状态、画像或简历的事实，模型必须先读取对应工具；Provider 失败时返回明确错误而不使用 Fixture 伪装。上下文限制为最近 12 条消息及少量近期成功工具结果，避免将整段历史或整份简历不断塞入 Prompt。

## 5. SSE 约定

Agent 使用 POST SSE，事件至少包含：

```text
run_started
tool_started
tool_completed
assistant_delta
assistant_completed
run_failed
action_proposed
action_resolved
```

每个事件有数据库 ID、`run_id`、运行内递增 `sequence`、状态和可选 JSON `payload`。前端展示用户可理解的工具进度、来源和待确认卡片；不展示隐藏推理、原始 Prompt、密钥或未脱敏的简历联系字段。运行以 `assistant_completed` 或 `run_failed` 结束；持久化事件可通过会话事件接口读取。

第一版搜索和岗位分析在 Agent 请求内同步执行，并受配置的模型超时与工具调用上限约束。批量岗位同步量增大后，再考虑任务队列。

## 6. 隐私和配置

- 手机号、邮箱、身份证和详细住址不发送给 LLM。
- 简历附件只在用户主动同意解析后，将脱敏文本发送给已配置模型；原文件不上传。
- API Key 只从 `.env` 或本地安全配置读取，不写入前端、日志或普通业务表。
- 本地数据库和简历文件默认只服务单用户。
- Provider 来源、授权方式、条款链接和失败状态必须可追溯。
