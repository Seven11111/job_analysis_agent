# Job Analysis Agent API 契约

本文档约束 FastAPI 的公开接口、请求响应结构、错误码和 Agent SSE 事件。产品范围见 [PRD.md](../PRD.md)，技术实现见 [architecture.md](architecture.md)，数据库字段见 [data-model.md](data-model.md)。

## 1. 通用约定

- Base URL：`/api/v1`。
- 第一版是本地单用户应用，不做登录鉴权；接口默认使用当前 active profile。
- JSON 请求使用 `Content-Type: application/json`。
- 日期使用 `YYYY-MM-DD`，例如 `2026-09-20`。
- 时间使用带时区的 ISO 8601，页面按 `Asia/Shanghai` 展示，例如 `2026-09-20T14:30:00+08:00`。
- ID 使用整数；`run_id`、`session_id` 等运行标识使用字符串。
- 分页默认 `page=1`、`limit=20`，`limit` 最大为 100。
- 业务 JSON 字段保持结构化返回，不把 JSON 字符串再次嵌套在响应里。

通用错误响应：

```json
{
  "detail": {
    "code": "validation_error",
    "message": "请求参数不合法",
    "field_errors": {
      "city": "城市不能为空"
    }
  }
}
```

通用错误码：

| HTTP | code | 使用场景 |
|---:|---|---|
| 400 | `invalid_request` | 请求语义不合法 |
| 404 | `not_found` | 岗位、收藏、画像或会话不存在 |
| 409 | `already_exists` | 重复收藏、重复导入或状态冲突 |
| 422 | `validation_error` | Pydantic 参数校验失败 |
| 502 | `provider_unavailable` | Provider 全部不可用 |
| 502 | `generation_failed` | LLM 调用或结构化解析失败 |
| 500 | `persistence_failed` | 数据库写入失败 |

## 2. 健康检查

### `GET /health`

响应 `200`：

```json
{
  "status": "ok",
  "timestamp": "2026-09-20T14:30:00+08:00",
  "database": "ok",
  "providers": {
    "fixture": "available",
    "manual_link": "available",
    "boss_agent_cli": "available",
    "job_pro": "available",
    "offer_xiansheng": "configured"
  }
}
```

## 2.1 BOSS 本地登录引导

BOSS 登录由用户在本机官方页面完成，学习项目不接收账号、密码、短信验证码、Cookie 或 Token。后端默认启动独立的可见 Chrome CDP 窗口，并以 `boss login --cdp` 强制使用该会话；岗位搜索复用 CLI 登录态并通过其只读 `search` 命令获取岗位。若 CLI 提供 `--browser-source`，会显式传入 `existing-browser`；若没有，则不传不支持的参数，仍要求 CDP 地址且登录命令必须具备 `--cdp`。后端只负责启动本机登录流程、读取脱敏后的进度、并通过 SSE 返回状态。

适配器不假定 CLI 版本号代表参数一定存在：首次检查时读取 `boss --version`、`boss --help`、`boss search --help`、`boss login --help`，根据实际能力构造命令。启用 BOSS 前必须确认 CLI 支持全局 `--cdp-url`、`--json`，搜索支持 `--city`、`--job-type`、`--no-cache`，登录支持 `--cdp`、`--timeout`。能力不满足时 `/providers/boss/status` 返回 `status: incompatible`，不启动登录或搜索。`--browser-source existing-browser` 是可选能力；部分上游版本只提供 `--cdp-url`，适配器会兼容这一差异，而不会向 CLI 传入未知参数。`BOSS_CLI_COMMAND` 可填写命令名或可执行文件绝对路径；搜索强制限定为实习并跳过 CLI 搜索缓存。CLI 更新后会自动重新探测。

本机安装方式（从项目根目录运行）：

```bash
bash scripts/install_provider_tools.sh boss
```

安装脚本将固定版本的 CLI 安装到 `.tools/uv/`，可执行文件位于 `.tools/bin/boss`。`BOSS_CLI_COMMAND` 默认指向该项目相对路径；所有带路径的命令都会锚定到项目根目录，不要求全局 `PATH`。如自定义安装位置，在 `.env` 设置 `BOSS_CLI_COMMAND` 为命令名或可执行文件路径，再重启后端。完整配置见[配置指南](../configuration.md)。

### `GET /providers/boss/status`

返回当前本机 CLI 和登录态状态：

```json
{
  "provider": "boss_agent_cli",
  "installed": true,
  "authenticated": false,
  "status": "browser_session_missing",
  "message": "本机登录缓存存在，但项目 Chrome 中没有可复用的 BOSS 页面；请打开 Chrome 登录页后再搜索",
  "active_login_id": null,
  "can_start": true
}
```

### `POST /providers/boss/login/start`

启动一个本地、用户主动触发的 `boss login` 进程；若项目专用 Chrome 尚无 BOSS 页面，会在该 Chrome 中打开官方登录页。接口只返回任务标识，不返回任何登录凭据：

```json
{
  "run_id": "boss_login_xxx",
  "status": "waiting_user",
  "message": "登录流程已启动，请在官方 BOSS 页面完成扫码或手机号登录",
  "reused": false
}
```

前端随后订阅：

```text
GET /providers/boss/login/{run_id}/events
```

事件类型统一为 `boss_login`，数据包括 `started`、`progress`、`succeeded`、`failed`、`canceled`。登录成功后前端重新查询 `/providers/boss/status`。`authenticated=true` 要求 CLI 报告已登录，且配置的 CDP Chrome 中存在真实的 BOSS 页面标签；仅调试端口在线或本地缓存残留不算可用。使用可见 Chrome CDP 时，即使 CLI 本地缓存标记为 `partial/degraded`，只要 BOSS 页面和登录态仍可复用，也允许只读搜索。搜索提交时会重新检查状态；会话缺失时先启动 Chrome 登录流程并保留当前搜索条件，用户完成登录后再次点击搜索。若实际搜索返回环境风控或会话失效，页面保留 Provider 失败原因，不静默切换到 Fixture。收到 BOSS `code 37` 后进入本地冷却窗口，并停止同一轮剩余城市请求，避免重复触发风控；项目不尝试绕过验证。

### `POST /providers/boss/login/{run_id}/cancel`

取消当前本地登录进程。登录窗口、Cookie、Token 和手机号都不会进入学习项目数据库。

## 3. 岗位搜索和岗位详情

### `POST /jobs/search`

`city` 为兼容旧客户端保留；新客户端使用 `cities` 传入多个城市。`providers` 已支持多个来源，服务会分别调用并合并去重，单个来源失败不会阻断其他来源。

当前真实只读来源包括：

- `boss_agent_cli`：通过用户已登录的可见浏览器/CDP 读取 BOSS，只读搜索；受到平台风控时会透明返回失败，不绕过验证。
- `job_pro`：通过 [job-pro](https://github.com/HA7CH/job-pro) 调用公司公开招聘接口，默认范围为中国实习岗位，不需要 BOSS 登录。它返回官方职位链接和岗位基础信息，但部分来源没有明确发布日期，因此 `published_date` 会是 `null`，使用 `published_range=all` 才不会因日期未知被排除。
- `fixture`：离线示例，仅用于开发和回归测试。

安装 `job-pro` 后即可启用真实公开来源：

```bash
bash scripts/install_provider_tools.sh job-pro
```

安装脚本将固定版本安装在 `.tools/job-pro/`，`JOB_PRO_COMMAND` 指向其本地可执行文件。默认扫描字节跳动、腾讯、阿里巴巴、美团、小红书、京东、快手、百度、华为、小米、网易、滴滴、哔哩哔哩、拼多多和米哈游。可通过 `JOB_PRO_COMPANIES` 调整扫描列表。项目只解析 CLI 已返回的 JSON，不负责突破网站限制，不自动投递，也不会把搜索结果自动写入数据库。

请求：

```json
{
  "keyword": "后端实习",
  "company": "小红书",
  "cities": ["上海", "杭州"],
  "published_range": "3d",
  "salary_mode": "any",
  "salary_min": null,
  "internship_type": "不限类型",
  "education": null,
  "internship_months": null,
  "days_per_week": null,
  "conversion_chance": null,
  "providers": ["job_pro", "boss_agent_cli"],
  "sort_by": "recommended",
  "page": 1,
  "limit": 20
}
```

字段规则：

- `published_range`：`all`、`1d`、`3d`、`7d`、`30d`。
- `salary_mode`：`any`、`disclosed_only`、`minimum`。
- `company`：可选公司名称筛选；求职 Agent 会将公司、职位关键词和城市分别传入。job-pro 来源会将已配置的公司名映射为对应来源 ID 定向查询，其他来源则在结果中按公司名筛选。
- `salary_min` 只有 `salary_mode=minimum` 时生效；未公开薪资不能满足最低薪资条件。
- `published_range` 不是 `all` 时，没有 `published_date` 的岗位必须排除。
- `providers` 为空时使用配置中启用的 Provider；`page` 与 `limit` 用于分页，岗位搜索页面支持页码按钮、直接跳页和每页数量调整。
- `sort_by` 支持 `recommended` 和 `newest`。`recommended` 按当前已确认求职偏好与当前在线简历进行本地规则排序；没有画像/简历资料时透明回退到发布日期排序，不生成虚假匹配分。当前关键词、公司、城市、来源、日期及其他显式筛选先执行，不会被画像放宽或覆盖。
- 搜索响应包含 `recommendation_context` 和每条岗位的 `recommendation`：匹配参考分、匹配点、待核对点、未知信息及反馈。匹配依据来自岗位标准字段/公开描述与画像/当前在线简历；不调用 LLM，不表示录用概率。附件简历只有在用户确认解析并成为当前在线简历后才参与排序。

搜索响应中的 `recommendation_context` 标识排序方式以及是否读取求职偏好/当前在线简历。每条临时岗位结果的 `recommendation` 包含 `score`（可为空）、`label`、`matched_points`、`missing_points`、`unknown_points` 和 `feedback`。

### `PUT /jobs/search-results/{result_token}/feedback`

对当前临时搜索结果记录反馈，可改为另一选项或传 `null` 撤销：

```json
{"feedback": "interested"}
```

`feedback` 取 `interested`、`not_interested` 或 `null`。在智能排序下，感兴趣结果前置、不感兴趣结果后置；选择最新排序时反馈不改变顺序。反馈只保存在服务进程的临时搜索结果中，不进入数据库、不自动改变求职画像或岗位状态；服务重启后清除。结果不存在或进程重启后再次提交会返回 `404 search_result_expired`。

### Offer 先生校招资讯（独立于实习岗位）

Offer 先生返回招聘公告级数据，不属于 `/jobs/search` 的 `JobRecord`，不会写入岗位库。服务端读取 `OFFER_XIANSHENG_API` 并以 `Authorization: Bearer ...` 调用官方搜索接口；密钥不返回前端。搜索支持关键词、公司、职位/职能、行业、城市、届别、学历、企业性质、招聘批次和网申时间范围，具体字段映射遵从[官方搜索接口](https://developer.offerxiansheng.com/docs/api/search)。

`GET /providers/offer-xiansheng/status` 只返回 `configured` 配置状态，不发起网络请求，也不代表远端连通已验证。

`POST /campus-recruit/search` 请求示例：

```json
{
  "keyword": "算法",
  "company": "示例科技",
  "cities": ["杭州", "上海"],
  "graduation_year": 2027,
  "recruitment_batch": "秋招,提前批",
  "start_time": "2026-08-01",
  "end_time": "2026-10-31",
  "limit": 20
}
```

招聘批次可多选，`recruitment_batch` 用英文逗号连接选项值。首次请求不传 `cursor`；下一页将上次响应的 `next_cursor` 原样放回请求。Offer 先生采用游标分页且不返回总数，因此前端只把已读取的页码作为页码按钮，不虚报总页数；输入未读取的页码时，会按游标顺序连续读取中间页，直到目标页或数据末页。跳转到较远页码可能触发多次上游请求。`limit` 范围为 1–100。

响应示例：

```json
{
  "items": [{
    "id": "encrypted_unique_id",
    "recruit_info_name": "2027届秋招",
    "company_name": "示例企业有限公司",
    "graduation_year": 2027,
    "recruitment_batch": "秋招",
    "position_categories": ["技术岗", "产品岗"],
    "cities": ["杭州", "上海"],
    "application_start_date": "2026-08-01",
    "application_end_date": "2026-10-31",
    "content": "公告纯文本……",
    "application_url": "https://example.com/apply",
    "announcement_url": "https://example.com/notice",
    "release_source": "官网",
    "updated_at": "2026-08-31 09:30:00"
  }],
  "count": 1,
  "limit": 20,
  "next_cursor": "opaque_cursor",
  "has_more": true,
  "source": {"provider": "offer_xiansheng", "name": "Offer 先生校招资讯", "data_type": "campus_recruit_notice"}
}
```

字段边界：`graduation_year` 来自官方 `date` 届别字段，不是发布日期；薪资和具体岗位标题不由公告名称或职位类别推断。官方 `richText` 不作为 HTML 返回或渲染；链接仅接受 HTTPS。搜索结果不会自动写数据库，用户需核实具体岗位后再使用手动岗位链接导入。

错误响应：未配置密钥返回 `503 provider_not_configured`；远端额度或频率限制返回 `429 provider_quota_exhausted` / `provider_rate_limited`，不自动重试；凭证错误、超时、网络错误或非预期响应返回明确 Provider 错误。官方错误码与重试约束见[分页与错误处理](https://developer.offerxiansheng.com/docs/common/pagination-errors)和[调用限制](https://developer.offerxiansheng.com/docs/common/rate-limit)。

响应 `200`：

```json
{
  "items": [
    {
      "id": 101,
      "title": "Python 后端开发实习生",
      "company_name": "示例科技",
      "city": "上海",
      "district": "浦东新区",
      "job_type": "实习生",
      "published_date": "2026-09-18",
      "salary": {
        "min": null,
        "max": null,
        "unit": null,
        "status": "undisclosed",
        "display": "薪资未公开"
      },
      "internship_months": 3,
      "days_per_week": 4,
      "conversion_chance": "unknown",
      "detail_url": "https://example.com/jobs/101",
      "source": {
        "name": "Fixture",
        "provider": "fixture",
        "quality_status": "healthy"
      },
      "is_saved": false,
      "application": null,
      "latest_match": null
    }
  ],
  "total": 1,
  "page": 1,
  "limit": 20,
  "quality": {
    "undisclosed_salary_count": 1,
    "missing_published_date_count": 0,
    "providers": [
      {"provider": "fixture", "status": "success", "count": 1}
    ]
  }
}
```

### `GET /jobs/{job_id}`

返回岗位当前标准化信息、最新快照、来源信息、收藏关系和最新匹配摘要。不存在返回 `404 not_found`。

### `GET /jobs/search-results/{result_token}`

查询本次搜索产生的临时结果。搜索结果不会自动写入数据库，进程重启或缓存过期后需要重新搜索。

### `POST /jobs/search-results/{result_token}/save`

用户确认后将临时结果写入 `jobs` 和 `job_snapshots`，返回持久化后的岗位详情。之后可以通过 `POST /applications` 建立用户收藏关系。

### `POST /jobs/import`

请求：

```json
{
  "detail_url": "https://campus.example.com/job/101",
  "title": "后端开发实习生",
  "company_name": "示例科技",
  "city": "上海",
  "job_type": "实习生",
  "description": "岗位描述原文",
  "requirements": "任职要求原文",
  "published_date": "2026-09-18",
  "salary_status": "undisclosed"
}
```

响应返回标准化后的 `job` 和 `snapshot`。用户主动导入是合规来源，必须保留 `source=manual`。

当前实现拆成两步：

```text
POST /jobs/import/preview
POST /jobs/import/{preview_token}/confirm
```

第一步只读取公开页面并返回提取草稿；第二步才写入 `jobs` 和 `job_snapshots`。提取链路适用于不同招聘网站：先解析 JSON-LD；若页面是 JavaScript 外壳、可见正文不足，或静态 HTTP 遇到连接/DNS 类传输错误，再尝试普通 Playwright 渲染；401/403/429 等拒绝或限流状态不重试。之后由已配置的 LLM 仅根据已读取的可见正文抽取字段。每个模型字段必须附带可在页面正文核对的原文证据，缺少证据的字段会被丢弃；页面更新时间不会当作发布日期，未知薪资不会记为 0。模型无法确认具体岗位或关键证据不足时，接口返回友好错误，不用域名伪装公司名。预览仍只存于进程内临时缓存，确认前不写数据库。

动态页面解析需要安装 Playwright 浏览器：

```bash
.venv/bin/python -m playwright install chromium
```

未安装浏览器时仍会尝试静态 HTML 和 LLM 提取；若静态正文不足，预览会明确失败。HTTP 403、登录页、验证码或站点限制不会通过浏览器重试或绕过。未配置 LLM 时，仅含完整 Schema.org `JobPosting` 数据的页面可以直接预览，其他页面返回 `503 llm_not_configured`；模型请求失败返回 `502 generation_failed`。

### `POST /jobs/{job_id}/refresh`

刷新指定岗位的来源快照。只允许合规 Provider 执行；返回新的快照或明确的 Provider 错误。

## 4. 岗位管理和状态

### `GET /applications`

查询参数：

```text
tab=all|pending_analysis|analyzed
status_id=<integer，可选>
q=<岗位名称或公司名称关键词，可选>
city=<城市名称，可选，支持包含匹配>
page=1
limit=20
```

岗位管理页面组合分析状态、当前自定义状态、岗位/公司关键词和城市筛选；`q` 同时匹配岗位名称与公司名称。

响应：

```json
{
  "items": [
    {
      "id": 501,
      "job": {"id": 101, "title": "后端开发实习生", "company_name": "示例科技"},
      "current_status": {"id": 1, "name": "已保存", "color": "blue"},
      "saved_at": "2026-09-20T10:00:00+08:00",
      "last_status_changed_at": "2026-09-20T10:00:00+08:00",
      "note": "先收藏，补充项目后再投递",
      "latest_match": null
    }
  ],
  "total": 1,
  "page": 1,
  "limit": 20
}
```

### `POST /applications`

请求：

```json
{
  "job_id": 101,
  "status_id": null,
  "note": "先收藏，补充项目后再投递"
}
```

`status_id=null` 时使用当前画像的默认“已保存”状态。重复收藏返回 `409 already_exists`。

### `GET /applications/{application_id}`

返回收藏关系、岗位详情、当前状态、最新匹配分析摘要和备注。

### `PATCH /applications/{application_id}`

只修改收藏关系的备注等非状态字段：

```json
{"note": "准备好简历后投递"}
```

状态变更必须使用专用接口，避免绕过历史记录。

### `POST /applications/{application_id}/status`

请求：

```json
{
  "to_status_id": 3,
  "effective_at": "2026-09-22T09:00:00+08:00",
  "note": "收到 HR 一面邀请"
}
```

响应同时返回更新后的 `application` 和新增的 `status_event`。服务端必须在同一事务内更新当前状态和历史事件。

### `GET /applications/{application_id}/timeline`

按 `effective_at` 倒序返回完整状态历史。时间来自用户设置，不由系统推断。

### `PATCH /applications/{application_id}/timeline/{event_id}`

允许用户修订任一历史事件的状态、生效时间和备注。传入的带时区时间会先转换为 UTC 保存；修订后，系统按事件录入顺序重建 `from_status` 链和当前状态，生效时间只决定时间线展示顺序。

### `DELETE /applications/{application_id}`

从个人岗位管理中移除该跟踪关系及其状态时间线。岗位主记录、来源快照和岗位匹配分析不会删除，因此不会破坏共享岗位资料或历史分析。

### 状态定义接口

```text
GET    /applications/status-definitions
POST   /applications/status-definitions
PATCH  /applications/status-definitions/{status_id}
DELETE /applications/status-definitions/{status_id}
```

状态删除采用停用而非物理删除，已有历史事件仍然保留。初次使用时系统创建一组默认状态，但用户可以新增、修改和停用状态；系统不会根据岗位搜索或模型结果自动修改当前状态。

### 求职工作台接口

工作台概览和用户主动维护的待办、面试安排使用以下接口。所有列表仅返回当前本地画像的数据；关联的 `application_id` 必须属于该画像。工作台读写不把面试记录解释为岗位状态，也不自动修改岗位跟踪状态。

```text
GET    /workbench/overview
GET    /workbench/todos?status=open|completed|all&page=1&limit=100
POST   /workbench/todos
PATCH  /workbench/todos/{todo_id}
DELETE /workbench/todos/{todo_id}
GET    /workbench/interviews?start_at=<ISO8601>&end_at=<ISO8601>
POST   /workbench/interviews
PATCH  /workbench/interviews/{interview_id}
DELETE /workbench/interviews/{interview_id}
```

待办请求示例：

```json
{
  "title": "准备技术面试",
  "application_id": 501,
  "due_at": "2026-10-20T18:00:00+08:00",
  "priority": "high",
  "note": "复习项目中的检索和 Agent 设计"
}
```

面试安排请求示例：

```json
{
  "title": "技术一面",
  "application_id": 501,
  "starts_at": "2026-10-21T14:00:00+08:00",
  "ends_at": "2026-10-21T15:00:00+08:00",
  "timezone": "Asia/Shanghai",
  "interview_format": "online",
  "meeting_url": "https://example.com/meeting"
}
```

创建/修改时提交的时间必须包含时区，持久化为 UTC；页面按北京时间展示。截止时间、公司、岗位和备注等可选字段可以显式传 `null` 清空。结束时间必须晚于开始时间。若删除 `applications` 跟踪关系，关联的待办和面试安排通过 `ON DELETE SET NULL` 保留，并不删除用户的个人计划。

`GET /workbench/overview` 返回以下可核对的统计：当前跟踪岗位总数、待处理/逾期/已完成待办数、未来面试数、未来 7 天面试数、按用户状态定义统计的当前岗位分布，以及最近 6 周按北京时间自然周统计的状态事件数。它不计算自定义状态的转化率，不把搜索结果视为已保存或已投递岗位。

## 5. 用户画像、简历和记忆

### `GET /profile`

返回当前画像、当前简历摘要、active profile facts 和可用状态定义。敏感联系方式默认不返回给前端 Agent 上下文。

### `PUT /profile`

更新用户主动填写的画像字段：

```json
{
  "school": "某大学",
  "major": "计算机科学",
  "education": "本科",
  "graduation_year": 2027,
  "target_directions": ["后端", "AI 应用"],
  "target_cities": ["上海"],
  "available_period": "2026 年暑期",
  "days_per_week": 4,
  "internship_months": 3,
  "desired_industries": ["互联网", "AI"]
}
```

### `GET /profile/facts`

支持 `status=active|superseded|temporary|deleted` 筛选，默认只返回 active。

### `POST /profile/facts`

支持直接写入已确认事实，也支持先写入 temporary 事实再通过 `/profile/confirm` 确认：

```json
{
  "fact_type": "skill",
  "fact_key": "python",
  "fact_value": "熟悉 Python 和 FastAPI",
  "source": "user",
  "confirmed": true
}
```

### `PATCH /profile/facts/{fact_id}` / `DELETE /profile/facts/{fact_id}`

修改或逻辑删除单条画像事实。删除不物理删除历史记录，而是更新 `status=deleted`。

### `POST /profile/confirm`

确认 Agent 生成的画像摘要：

```json
{
  "fact_ids": [12, 13],
  "replace_fact_ids": [5]
}
```

服务端确认后才把事实标记为 active，并将被覆盖的旧事实标记为 superseded。

### 简历版本接口

```text
GET  /profile/resumes
POST /profile/resumes
GET  /profile/resumes/{resume_id}
POST /profile/resumes/{resume_id}/select
POST /profile/resume-attachments/parse
GET  /profile/resume-attachments
POST /profile/resume-attachments/{attachment_id}/confirm
GET  /profile/resume-attachments/{attachment_id}/file
DELETE /profile/resume-attachments/{attachment_id}
```

简历正文仅保存在本地数据库；列表响应只返回脱敏后的短预览，不返回完整正文。首个简历版本自动成为当前版本，之后必须由用户主动切换当前版本。

附件上传使用 `multipart/form-data`，字段为 `file` 和 `consent_to_model=true|false`。第一版只接收 PDF/DOCX，单文件最大 10 MB。服务端在本机提取文本；用户必须明确同意后，才将脱敏后的简历文字发送给当前配置的 LiteLLM 模型。原始文件不发送给模型。

解析接口返回待确认草稿，不返回完整原文，也不自动创建简历版本：

```json
{
  "id": 12,
  "original_filename": "backend-resume.pdf",
  "content_type": "application/pdf",
  "size_bytes": 84231,
  "sha256": "…",
  "parse_status": "pending_review",
  "linked_resume_version_id": null,
  "draft_content": {
    "basics": {"full_name": "张同学", "phone": "13800000000", "email": "student@example.com", "city": "上海", "school": "某大学", "major": "计算机科学", "education": "本科", "graduation_year": 2027},
    "job_intent": {"target_positions": ["后端开发实习生"], "target_cities": ["上海"], "internship_type": "日常实习", "availability": "两周内", "days_per_week": 4, "expected_salary": null},
    "education": [],
    "campus_experiences": [],
    "experience": [],
    "projects": [],
    "skills": ["Python", "FastAPI"],
    "certificates": [],
    "summary": null
  }
}
```

在线简历的 `structured_content` 与该草稿使用同一 JSON 契约，支持从空白表单创建。姓名/手机号/邮箱在本机提取后仅回填给草稿，不进入模型 Prompt；求职意向中的期望薪资是简历资料字段，不参与岗位搜索筛选。

前端允许用户编辑 `draft_content`，然后调用 `POST /profile/resume-attachments/{attachment_id}/confirm`，提交 `title`、完整的 `structured_content` 和 `set_current`。确认后服务端从本地附件记录读取原文，创建新的 `resume_versions` 行并关联 `source_attachment_id`；旧版本不覆盖。`GET /profile/resume-attachments` 仅对 `pending_review` 返回草稿，已确认附件不再重复返回草稿。

`DELETE /profile/resume-attachments/{attachment_id}` 只删除附件文件和附件记录，已确认的在线简历、简历原文及历史岗位分析继续保留；关联简历的来源外键置空。`GET /profile/resumes/{resume_id}` 返回当前本地简历详情，供前端编辑后另存新版本。

附件解析错误：未同意模型处理返回 `400 consent_required`；格式、大小或文字提取失败返回 `422 invalid_resume_file`；未配置模型返回 `503 llm_not_configured`；模型调用或结构化输出失败返回 `502 generation_failed`。模型失败时不保存附件或解析草稿。

### 画像记忆规则

- `temporary`：临时提取或用户尚未确认的事实，不进入默认画像上下文。
- `active`：用户确认后可用于后续搜索和岗位分析的事实。
- `superseded`：被新的方向或事实替代，但保留历史记录。
- `deleted`：用户主动删除，只做逻辑删除。
- 手机号、邮箱、身份证号和详细住址在进入未来 LLM Prompt 前必须经过脱敏函数。

## 6. 岗位匹配分析

### `POST /jobs/{job_id}/analyze`

请求：

```json
{
  "resume_version_id": 4,
  "force_refresh": false
}
```

第一版同步返回：

```json
{
  "match_id": 801,
  "job_id": 101,
  "match_score": 85,
  "recommendation": "strong_match",
  "matched_points": ["具备 Python 后端基础", "有 FastAPI 项目经历"],
  "missing_points": ["缺少大规模系统实践"],
  "risk_points": ["岗位要求每周到岗 4 天"],
  "next_actions": ["补充项目中的性能优化细节"],
  "source_evidence": [
    {"label": "岗位要求", "url": "https://example.com/jobs/101"}
  ],
  "model_used": "openai/example-model",
  "created_at": "2026-09-20T14:30:00+08:00"
}
```

LLM 调用失败或结构化报告校验失败返回 `502 generation_failed`，不创建成功的 `job_matches`。

### `POST /jobs/{job_id}/matches`

用户主动触发岗位分析。岗位必须已经保存；服务端读取当前求职画像、已确认画像事实、当前简历（如存在）和最新岗位快照，使用规则初筛作为辅助证据，再由配置的 LiteLLM 模型生成结构化匹配报告。手机号、邮箱、身份证号和常见详细住址在进入 Prompt 前脱敏。

`LITELLM_PROVIDER` 用于指定 LiteLLM 路由 Provider，适配 OpenAI 兼容服务时设置为 `openai`；适配器会在裸模型 ID 前添加 Provider 前缀。未配置 `LITELLM_MODEL` 返回 `503 llm_not_configured`；模型调用失败或输出无法通过结构化校验返回 `502 generation_failed`，不创建成功的 `job_matches`。

### `GET /jobs/{job_id}/matches`

返回该岗位的匹配分析历史，按 `created_at` 倒序。

### `GET /matches/{match_id}`

返回完整结构化匹配报告、使用的简历版本、岗位快照时间和来源证据。

## 7. 岗位订阅与查新

订阅只能引用岗位搜索页已接入的岗位来源 `boss_agent_cli`、`job_pro`；校招公告来源和离线 Fixture 不接受。查新仅在本机 API 进程运行期间执行，结果临时保留 30 天，不发 QQ、邮件或其他外部通知。

### `GET /subscriptions`

返回当前单用户的订阅列表及每条订阅最近一次运行摘要。

### `POST /subscriptions`

创建岗位查新。`filters` 使用 `POST /jobs/search` 的当前条件结构，并必须包含至少一个有效岗位 Provider。

```json
{
  "name": "杭州 Agent 实习",
  "filters": {
    "keyword": "Agent",
    "cities": ["杭州"],
    "published_range": "3d",
    "salary_mode": "any",
    "providers": ["job_pro"],
    "sort_by": "newest"
  },
  "frequency": "daily",
  "schedule_time": "09:00",
  "weekday": null,
  "interval_days": null,
  "month_day": null
}
```

`frequency` 可为 `manual`、`daily`、`weekdays`、`weekly`、`interval` 或 `monthly`。所有定时计划使用北京时间 `schedule_time`，格式为 24 小时制 `HH:mm`，精确到分钟、不支持秒；本地调度器按分钟边界检查。周计划使用 ISO 星期编号（周一 `1` 至周日 `7`），间隔计划的 `interval_days` 为 2–30，每月计划的 `month_day` 为 1–31（短月按当月最后一天执行）。响应返回归一化条件、周期参数、启停状态、下一次运行时间及最新运行信息。

### `GET /subscriptions/{subscription_id}` / `PATCH /subscriptions/{subscription_id}` / `DELETE /subscriptions/{subscription_id}`

读取、部分更新或删除当前用户的查新条件。更新支持 `name`、`filters`、`frequency`、`schedule_time`、`weekday`、`interval_days`、`month_day`、`enabled`。删除会清除该订阅的查新记录和去重键，不删除已保存到岗位管理的岗位、快照或投递记录。

### `POST /subscriptions/{subscription_id}/runs`

立即同步运行一次查新，返回运行摘要。Provider 全部失败时也返回记录，`status` 为 `failed`，错误放在 `provider_results` 和 `error_message` 中；部分来源失败时为 `partial_failed`。`no_new` 表示来源正常但没有新岗位。

### `GET /subscriptions/{subscription_id}/runs` / `GET /subscriptions/{subscription_id}/runs/{run_id}`

分页查询运行记录及该次岗位预览。运行详情接受 `page`、`limit`（最大 100），每项包含原始 Provider 和岗位来源链接。岗位预览保留 30 天；运行摘要和用于去重的哈希保留到删除订阅。

### `POST /subscriptions/items/{item_id}/save`

用户确认后，将一条查新预览写入 `jobs`、`job_snapshots` 和 `applications`。重复点击幂等返回同一岗位/跟踪记录；搜索或定时查新本身不会写岗位库。

错误码：`404 subscription_not_found` 表示订阅/运行/预览不存在或已过期；`409 subscription_running` 表示同一订阅正在查新；`422 invalid_subscription` 表示来源或条件无效。

## 8. 求职 Agent

### `GET /agent/tools`

返回当前注册的工具名称、说明和 JSON 参数 Schema。工具按业务能力分组如下（以接口运行时返回为准）：

- 岗位与推荐：`search_jobs`（服从岗位搜索页所选来源，支持分页）、`preview_job_link`、`set_job_recommendation_feedback`、`list_saved_jobs`（关键词/城市/状态/分析情况/分页）、`get_saved_job_detail`、`compare_saved_jobs`、`get_application_status`、`analyze_saved_job`。
- 校招资讯与来源：`search_campus_recruit`（只读公告，不写入实习岗位库）、`get_provider_status`；仅在用户明确要求时，`start_boss_login` / `cancel_boss_login` 可启动或停止本机官方 BOSS 登录流程。
- 工作台与订阅：`get_workbench_overview`、`list_todos`、`list_interviews`；岗位订阅支持 `list_job_subscriptions`、`get_job_subscription`、`list_job_subscription_runs`、`get_job_subscription_run`、`run_job_subscription`。手动查新只产生临时预览，不自动保存岗位。
- 订阅写操作：`propose_job_subscription_create`、`propose_job_subscription_update`、`propose_job_subscription_delete` 均生成持久化确认卡片；确认前不创建、修改、暂停、恢复或删除订阅。创建/换来源仅可选岗位搜索页当前已勾选且后端可用的来源。删除只清除该订阅、查新历史和去重记录，不删除已保存岗位。
- 待办和面试新增、修改、删除以及其他业务写入均通过 `propose_*` 操作并要求用户确认。
- 画像和简历：`get_candidate_profile`、`list_profile_facts`、`get_current_resume`、`list_resume_versions`、`list_resume_attachments`；画像、记忆和简历操作通过确认流程。原始简历文件必须先在个人画像页面上传；Agent 不读取附件原文或私密联系方式。
- 投递状态：可新增/修改/停用自定义状态，并修改岗位当前状态、历史状态时间和备注；写入均需确认。
- 通用对话和历史会话由 Agent 会话与 SSE API 提供；岗位查新既可通过本节独立 API 和 `/jobs/subscriptions` 页面管理，也可由 Agent 查询、手动执行或通过确认卡片创建/调整/删除。

用户在 Agent 对话中提供招聘链接并请求查看、提取或分析时，Agent 调用 `preview_job_link`。该工具复用 `POST /jobs/import/preview` 的公开页面读取与字段提取逻辑，SSE 工具事件和助手消息会携带结构化预览及来源链接；预览不会写入岗位表。前端允许校对岗位名称、公司、城市、类型、发布日期、薪资和描述。用户明确申请收藏后，Agent 使用预览 token 和更正字段生成现有 `save_job` 待确认操作；只有用户确认后才写入岗位、快照和个人投递跟踪。无法访问、非岗位页面或站点限制会返回明确错误，不绕过登录、验证码或访问控制；网页文字按不可信数据处理。

`get_provider_status` 仅返回 BOSS 登录状态、job-pro 安装和已配置公司概况、Offer 先生配置状态，以及 LiteLLM Provider/模型名与是否已配置；不会返回任何密钥。Agent 发起的 BOSS 登录与 `/providers/boss/login/*` 共用同一个本地运行实例，因此岗位搜索页可继续显示状态和 SSE 进度。启动登录不等于登录成功，需等待用户在官方页面操作并再次查询状态。

待办和面试时间使用带时区 ISO 8601，输出转换为安排的时区或北京时间。岗位状态历史时间的 Agent 输入也必须带时区偏移，避免把本地时间误当 UTC。对岗位来源、待办、面试、状态、画像、简历或附件的创建、修改、删除和切换，Agent 必须先发出 `action_proposed` 并等待确认；取消不会写入。模型侧工具调用不允许直接修改数据库。

### `GET /agent/sessions`

返回当前单用户的历史会话摘要：`id`、`title`、`status`、`created_at`、`updated_at`、`message_count`。按最近更新倒序排列。

### `POST /agent/sessions`

新建空会话，可传可选 `title`。如果不提供，使用“新对话”；首次发消息时会自动改为消息主题。

### `PATCH /agent/sessions/{session_id}`

修改会话名称：`{"title":"上海后端实习"}`。

### `GET /agent/sessions/{session_id}`

返回会话摘要、用户/助手消息、最近 200 条运行事件，以及全部尚未处理的 `action_proposed` 事件（按事件 ID 顺序合并去重）。只读取当前本地画像关联的会话，避免较早创建但仍待确认的操作因事件数量上限而丢失。

### `POST /agent/chat/stream`

请求：

```json
{
  "session_id": 12,
  "message": "帮我找上海的 Agent 开发实习",
  "search_providers": ["boss_agent_cli", "job_pro"]
}
```

`session_id` 可省略；省略时创建新会话。`search_providers` 可省略以兼容旧客户端；网页端会发送岗位搜索页当前选择的来源，作为 Agent 本轮搜索的允许范围。该字段只影响 Agent 的 `search_jobs` 工具：用户明确指定来源时，Agent 可在 `providers` 参数中指定已选来源的子集；未指定时使用全部已选来源。后端拒绝任何未在网页端选择的来源，不会回退到其他来源。显式传入空数组时不会搜索，也不会回退到离线 Fixture，而会提示用户先选择来源。响应为 `Content-Type: text/event-stream`。每个事件保存到 `agent_run_events`，包含事件 ID、`run_id` 和递增 `sequence`：

若指定的会话仍有 `status=pending` 的确认操作，接口返回 `409 pending_action_confirmation`，不保存这条新消息，也不启动新一轮生成。若该会话的 Agent 运行仍在处理（例如操作已解决但模型尚未完成后续回答），接口返回 `409 run_in_progress`。待确认操作出现时，当前 SSE 运行会暂停在操作节点；用户确认或取消后，操作结果会返回给模型并继续生成本轮回答。若原运行已经中断，则操作处理后由用户主动发送下一条消息继续；被 409 拦截的消息不会自动重发。

```text
event: run_started
data: {"id":101,"run_id":"...","sequence":1,"type":"run_started","payload":{"session_id":12}}

event: tool_started
data: {"id":102,"run_id":"...","sequence":2,"type":"tool_started","name":"list_saved_jobs","payload":{"tool":"list_saved_jobs","parameter_summary":"页码：1"}}

event: tool_completed
data: {"id":103,"run_id":"...","sequence":3,"type":"tool_completed","payload":{"tool":"list_saved_jobs","summary":"找到已保存岗位","duration_ms":34}}

event: assistant_delta
data: {"id":104,"run_id":"...","sequence":4,"type":"assistant_delta","payload":{"text":"你目前保存了 3 个岗位。"}}

event: assistant_completed
data: {"id":105,"run_id":"...","sequence":5,"type":"assistant_completed","payload":{"message_id":9001,"text":"你目前保存了 3 个岗位。"}}
```

还支持 `action_proposed`、`action_resolved`。岗位保存、状态/备注修改、移除跟踪、订阅/待办/面试管理、画像修改和简历修改会先产生 `action_proposed`，状态为 `pending`；模型不会直接执行写操作。移除岗位只删除个人岗位管理中的收藏/跟踪关系及其状态历史，保留岗位来源数据、快照和分析历史。运行结束事件为 `assistant_completed`、`run_failed` 或 `run_cancelled`。文本按较小片段持续推送，停止事件会保留已生成的部分回答；失败事件包含面向用户的安全文案，不包含密钥、完整 Prompt 或第三方堆栈。

操作轨迹只包含工具名、白名单参数摘要、结果摘要、状态和工具执行耗时，不记录隐藏推理过程；自由文本备注、会议链接、简历内容等不会写入参数摘要。`duration_ms` 从工具开始执行到工具返回计算，不包含等待用户确认的停留时间。

### `POST /agent/sessions/{session_id}/runs/{run_id}/cancel`

请求停止该会话中正在运行的回答。响应状态为 `cancellation_requested`、`already_finished` 或 `not_running`。取消是协作式的：模型流会在下一段内容到达时停止；若当前正处于同步岗位来源请求中，则会在该调用返回后停止后续步骤。已生成文本会保存为标记 `structured_content.interrupted=true` 的助手消息，并记录 `run_cancelled` 事件。停止不是暂停/续写；用户可编辑输入，再发送一条新消息。

### `POST /agent/actions/{event_id}/resolve`

确认或取消一个待处理操作：

```text
{"confirm": true}
```

`confirm=false` 只取消提案；重复处理返回 `409 already_resolved`。确认后由后端调用现有岗位/画像/简历 Service，并唤醒等待该提案的 SSE 运行；移除操作只移除个人跟踪关系，不删除来源岗位、岗位快照或分析历史。简历修改创建新当前版本，并由本机保留原有姓名和联系方式。

### `GET /agent/sessions/{session_id}/events`

支持可选 `run_id`、`after_sequence` 和 `limit` 查询已保存事件，供历史对话回放；使用 `after_sequence` 时必须提供 `run_id`。不指定 `run_id` 时返回最近事件及所有仍待确认的操作；指定 `run_id` 时按运行内序号查询。当前 POST SSE 前端不自动重放断线流；刷新后可读取已经持久化的消息和事件。

Agent 支持一般对话及多轮上下文。模型每轮使用最近 12 条消息（单条最多 6000 字符），并选择性附加最近的成功工具证据；完整消息和事件仍保存在 SQLite，可通过会话接口切换和查看。此窗口不是无限上下文，也尚未实现自动摘要压缩。

## 9. 设置接口

### `GET /settings`

返回非敏感运行设置和凭据状态：

```json
{
  "llm": {"model": "openai/example-model", "configured": true},
  "providers": {"fixture": {"enabled": true}, "shixiseng": {"enabled": false, "configured": false}},
  "defaults": {"city": "上海", "published_range": "3d"},
  "memory_enabled": true
}
```

### `PATCH /settings`

只修改非敏感配置。API Key、App Secret 等密钥不接受在响应中回显，也不写入普通业务表。

## 10. 契约变更规则

- 新增字段优先采用可选字段，避免破坏前端。
- 删除字段或修改枚举必须同步更新 PRD、Schema、前端类型和测试。
- 错误 `code` 一经发布不随文案变化。
- SSE 新增事件必须保持旧事件字段兼容；事件顺序由 `sequence` 保证。
- 任何涉及岗位、状态、画像或匹配结果的接口变更，都必须同步更新 [data-model.md](data-model.md)。
