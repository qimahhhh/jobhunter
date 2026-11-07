# AI-Job-Hunter 后端

此目录包含 AI-Job-Hunter 黑客松 MVP 的 FastAPI 后端，当前提供两类工作流：

- `POST /api/v1/job-fit`：接收一次性画像和目标岗位，编排岗位校验、匹配分析、简历建议和面试题生成。
- `POST /api/v1/job-matches`：基于已持久化的用户画像和岗位执行硬约束过滤，再生成匹配结果。

当前代理行为由确定性实现模拟，稳定接口可直接替换为 MiMo 驱动的代理，而无需更改 API 契约。

## 运行

```powershell
python -m venv .venv
.\.venv\Scripts\python -m pip install -r requirements.txt
.\.venv\Scripts\python -m uvicorn backend.app.main:app --reload
```

也可以运行 `.\scripts\run_dev.ps1`。

打开 `http://127.0.0.1:8000/docs`。

应用默认使用 `sqlite:///./ai_job_hunter.db`；可通过 `DATABASE_URL` 覆盖数据库连接地址。首次启动会自动创建表并补齐 `jobs.employment_type` 字段。

## API 说明

| 方法与路径 | 说明 |
| --- | --- |
| `GET /health` | 健康检查。 |
| `POST /api/v1/job-fit` | 执行完整的岗位适配分析，并持久化成功结果；失败时返回带 `run_log` 的结构化错误。 |
| `GET /api/v1/job-fit`、`GET /api/v1/job-fit/{request_id}` | 查看分析历史或单次分析。 |
| `POST /api/v1/users`、`GET /api/v1/users/{user_id}` | 创建和查询用户；重复邮箱返回 `409`。 |
| `POST /api/v1/profiles`、`GET /api/v1/profiles/{profile_id}` | 创建或更新用户画像（一个用户只有一份，重复提交覆盖既有画像），并支持按 id 查询。 |
| `POST /api/v1/profiles/extract` | 提交简历纯文本，解析成 chunk 后让模型抽取画像草稿；返回证据引用、岗位方向建议、待补充问题与 degraded 标记，不落库。 |
| `POST /api/v1/profiles/extract/file` | 上传 PDF/DOCX 简历文件（请求体为文件字节，`filename` 查询参数决定解析器），响应与 `/profiles/extract` 相同。 |
| `POST /api/v1/profiles/extract/bundle` | 一次提交多来源：`resume_text`、`self_description`、`projects`（JSON，对象或数组）至少一项，合并后统一切块抽取；引用表头保留 `source` 标签，不落库。 |
| `POST /api/v1/profiles/extract/confirm` | 用户校对、修改抽取草稿后提交确认（人工确认节点），写入用户画像（重复确认更新同一份画像）；`recommended_roles` 存为 `suggested_roles`，用户保留或修改后的方向存为 `target_roles`，未修改时 `target_roles_source` 标为 `suggested`；草稿的 `missing_information` 一并落库；用户不存在返回 `404`。 |
| `POST /api/v1/resumes`、`GET /api/v1/resumes/{resume_id}` | 保存和查询来源类型及内容结构化的简历记录。 |
| `POST /api/v1/jobs`、`GET /api/v1/jobs`、`GET /api/v1/jobs/{job_id}` | 创建和查询岗位；列表支持 `employment_type` 筛选。 |
| `POST /api/v1/job-matches`、`GET /api/v1/job-matches/{match_id}` | 创建和查询匹配结果；创建前会按岗位类型、地点、薪资等硬约束过滤。 |

资源接口对不存在的 ID 返回 `404`；岗位不满足硬约束时，`POST /api/v1/job-matches` 返回 `422`，其中包含 `rejections` 和 `unknowns`。上传抽取接口对不支持的文件类型返回 `415`、空文件返回 `400`、超过 20MB 返回 `413`、模型未配置返回 `503`。

## 测试

```powershell
$env:PYTHONPATH = "."
python -m unittest discover -s backend/tests -v
```

## 画像输入预处理

`backend/app/chunking.py` 负责 Career Agent 的输入阶段：把简历 PDF/DOCX、结构化档案、自由文本统一成带来源标记的 block，再按段落聚成带 `chunk_id` 的 chunk，供模型结构化输出并回溯证据。该模块不调用模型，PDF/DOCX 解析库按需导入。

想确认解析结果，先 dump 再改提示词：

```powershell
.\.venv\Scripts\python scripts\dump_resume_chunks.py 简历.pdf
```

该脚本支持 PDF、DOCX、TXT 和 Markdown 文件。

API 侧的 `POST /api/v1/profiles/extract/file` 接收同样的 PDF/DOCX 简历文件：请求体是原始文件字节，`filename` 查询参数决定用哪个解析器，前端一次 `fetch` 即可上传；抽取结果与 `POST /api/v1/profiles/extract` 一致，不持久化。

`POST /api/v1/profiles/extract/bundle` 把简历文本、自然语言自述和项目 JSON 合并成一份上下文再抽取；`source` 标签保证引用能区分“我在哪实习”和“我的项目用了什么”。当渲染后的上下文超过预算（默认 6000 token），抽取会自动改为分组进行再合并：优先用一次模型调用合并局部草稿，合并失败则退化为去重拼接，保证不会因为截断提示词而静默丢内容。

## 后续计划

1. 接入真实岗位来源和来源验证。
2. 将模拟代理替换为 MiMo 客户端。
3. 持久化来源快照和失败信息。
4. 添加 React 工作台界面。
