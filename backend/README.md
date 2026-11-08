# AI-Job-Hunter 后端

`backend/` 是 FastAPI + SQLite 后端，负责简历解析、画像抽取与确认、岗位检索/匹配、简历草稿和面试题生成。模型默认走 DeepSeek 的 OpenAI 兼容接口，可替换为任意兼容服务。

## 运行

```powershell
uv sync
uv run uvicorn backend.app.main:app --reload --reload-dir backend
```

或使用 venv：

```powershell
python -m venv .venv
.\.venv\Scripts\python -m pip install -r requirements.txt
.\.venv\Scripts\python -m uvicorn backend.app.main:app --reload
```

打开 http://127.0.0.1:8000/docs。数据库默认 `sqlite:///./ai_job_hunter.db`，可通过 `DATABASE_URL` 覆盖。首次启动自动建表，并给旧库补齐 `jobs.employment_type`、`jobs.dedupe_key`、`jobs.last_seen_at` 等字段；`dedupe_key` 的唯一索引是尽力而为，旧库已有重复岗位时只警告、不阻止启动。

## 配置

| 变量 | 用途 |
| --- | --- |
| `DEEPSEEK_API_KEY` | 模型 Key，抽取/草稿接口必需；未配置返回 `503` |
| `DEEPSEEK_MODEL` | 默认 `deepseek-chat` |
| `DEEPSEEK_BASE_URL` | 默认 `https://api.deepseek.com` |
| `DATABASE_URL` | 默认 `sqlite:///./ai_job_hunter.db` |
| `OFFER_CAMPUS_API_KEY` | Offer先生校招数据开放平台 Key；未配置时 `/jobs/collect` 返回 `503` |
| `OFFER_CAMPUS_API_BASE` | 可覆盖采集接口地址 |

## API 说明

| 方法与路径 | 说明 |
| --- | --- |
| `GET /health` | 健康检查。 |
| `POST /api/v1/job-fit` | 执行完整的岗位适配分析，并持久化成功结果；失败时返回带 `run_log` 的结构化错误。 |
| `GET /api/v1/job-fit`、`GET /api/v1/job-fit/{request_id}` | 查看分析历史或单次分析。 |
| `POST /api/v1/users`、`GET /api/v1/users/{user_id}` | 创建和查询用户；重复邮箱返回 `409`。 |
| `POST /api/v1/profiles`、`GET /api/v1/profiles/{profile_id}` | 创建或更新用户画像（一个用户只有一份，重复提交覆盖既有画像），并支持按 id 查询。 |
| `POST /api/v1/profiles/extract` | 提交简历纯文本，解析成 chunk 后让模型抽取画像草稿；返回证据引用、岗位方向建议、待补充问题与 degraded 标记。传 `user_id` 时把切好的 chunk 存成简历记录并返回 `resume_id`，不传则完全无状态。 |
| `POST /api/v1/profiles/extract/file` | 上传 PDF/DOCX 简历文件（请求体为文件字节，`filename` 查询参数决定解析器，可选 `user_id` 同上），其余与 `/profiles/extract` 相同。 |
| `POST /api/v1/profiles/extract/bundle` | 一次提交多来源：`resume_text`、`self_description`、`projects`（JSON，对象或数组）至少一项，合并后统一切块抽取；引用表头保留 `source` 标签，可选 `user_id`。 |
| `POST /api/v1/profiles/extract/confirm` | 用户校对、修改抽取草稿后提交确认（人工确认节点），写入用户画像（重复确认更新同一份画像）；`recommended_roles` 存为 `suggested_roles`，用户保留或修改后的方向存为 `target_roles`，未修改时 `target_roles_source` 标为 `suggested`；草稿的 `missing_information` 一并落库；可带 `resume_id` 与 `evidence`；用户不存在返回 `404`。 |
| `POST /api/v1/resumes`、`GET /api/v1/resumes/{resume_id}` | 保存和查询来源类型及内容结构化的简历记录。 |
| `POST /api/v1/resumes/draft` | 用已存画像（外加画像关联的原简历 chunks）生成**基础简历**草稿，不涉及 JD；每条要点带 `sources` 引用，找不到原文依据的要点会被删除，数字对不上原文会进 `notes`。 |
| `POST /api/v1/jobs`、`GET /api/v1/jobs`、`GET /api/v1/jobs/{job_id}` | 创建和查询岗位；列表支持 `employment_type`、`verification_status` 筛选。手动录入不去重：同一公司同名岗位可以是两个真实岗位。 |
| `POST /api/v1/jobs/verify` | 批量记录人工核验结论（`active` / `expired` / `source_unavailable` / `pending_verification`）。只有人工给出结论时才会写 `last_verified_at`，改回 `pending_verification` 会同时清掉这个时间；整批一次提交，不存在的 id 进 `rejected` 而不影响其余。 |
| `POST /api/v1/jobs/ingest` | 采集器批量写入岗位，按 `公司 + 岗位名 + 城市` 去重：重复出现的岗位视为同一条，刷新薪资/地点/描述这些会变的字段并把 `last_seen_at` 更新为当前时间，首次来源保留为溯源。返回 `created` / `updated` 的 id 列表。 |
| `POST /api/v1/jobs/collect` | 从 Offer先生校招数据开放平台拉取最新公告并入库：归一化后走 `/jobs/ingest` 同一条幂等合并路径，返回 `source` / `fetched` / `created` / `updated` 和跳过原因。未配置 API Key 返回 `503`，来源不可用返回 `502`。 |
| `POST /api/v1/job-search` | Job Hunter Agent：在已入库岗位中检索并排序，返回 `candidates`（score、命中/缺失关键词、理由）和 `excluded`（被过滤的岗位及原因）。传 `profile_id` 时用画像的目标岗位、技能、城市、薪资下限补全查询，岗位类型**仅在画像里显式确认过**时才作为过滤条件；显式传入的字段优先。 |
| `POST /api/v1/job-hunt` | 一条请求跑完「检索 → 匹配 → 可选简历草稿」：`search` 是 `/job-search` 的结果，`matches` 是对候选前 `match_top` 条（默认 3）逐个生成的**已落库**匹配结果，`skipped` 记下“过了检索但没过画像硬约束”的候选及原因，`with_resume` 为真时再调 `/resumes/draft` 同一套逻辑。`run_log` 给每个阶段耗时，`profile_id` 不存在返回 `404`。 |
| `POST /api/v1/job-matches`、`GET /api/v1/job-matches/{match_id}` | 创建和查询匹配结果；创建前会按岗位类型、地点、薪资等硬约束过滤。 |

## 可追溯链

抽取接口带 `user_id` → 返回 `resume_id`（`GET /api/v1/resumes/{resume_id}` 的 `content.chunks` 里是当时切好的每一段）→ 确认时把 `resume_id` 和 `evidence`（chunk id 列表）一起写进画像。这样 `GET /profiles/{id}` 配合 `GET /resumes/{resume_id}`，就能把一条结论还原成简历原文的某一段；不带 `user_id` 则保持无状态草稿，什么都不写。

## 岗位召回

`backend/app/job_hunter.py` 的 `JobHunterAgent` 只做两件事：按查询里明确给出的硬约束过滤（没给的条件不启用），再按关键词重合度排序。岗位名称命中计双份；“查不到”和“没测量”分开表达：查询没有关键词时 score 记为 0.0 并在 `notes` 里说明。Agent 筛掉的岗位全部进 `excluded` 并带原因。

`services._narrow_job_query` 会把岗位类型、城市这类安全条件下推到 SQL，但会同时放行 `NULL` 行：字段缺失的岗位交给 Agent 报成 unknown，而不是在 SQL 层被静默当成不匹配。薪资需要跨周期换算，仍留在 Python 里比。

## 岗位去重与核验

`dedupe_key` 抹平大小写、空格、标点，以及城市写法（`北京市` = `北京`）和标题里的届别/急招类括号噪音（`AI 实习生（2026届）` = `AI 实习生`）。括号里是方向时不抹（`（算法）` ≠ `（工程）`）：误合并会丢一个真实岗位，误拆分至少看得见。只用于 `/jobs/ingest` 采集路径，手动创建仍一行一条。

`verification_status` 参与判断：Agent 会把 `expired` 的岗位从候选里剔除并写明原因；未核验 / 来源不可达的岗位仍然返回，但带 `warnings`；`verified_only=true` 时只检索 `active`。

## 采集

`backend/app/job_sources.py` 里 `OfferCampusSource` 负责抓取，`notices_to_jobs` 负责归一化。一条公告覆盖多个岗位，按 `content` 的岗位名拆成多条记录；公告标签带「实习」的记 `internship`，其余记 `full_time`。

来源 license 限定「仅限个人学习与研究，禁止批量落盘或再分发」，因此**公告正文（`richText`）永不入库**：只落企业、岗位、城市、学历、毕业年份这类事实字段和 `announcementUrl` 回链。采集由用户触发，不跑定时任务。

## 命令行

```powershell
.\.venv\Scripts\python scripts\job_data.py collect --limit 40   # 拉一批真实岗位并入库
.\.venv\Scripts\python scripts\job_data.py pending              # 打印待核验清单
.\.venv\Scripts\python scripts\job_data.py verify --ids <前缀> --status active
```

## 测试

```powershell
uv run pytest
```

也可以：

```powershell
$env:PYTHONPATH = "."
python -m unittest discover -s backend/tests -v
```
