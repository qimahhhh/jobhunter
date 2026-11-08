# Job Hunter

AI 求职决策与执行平台：上传简历 → 建立档案 → 匹配岗位 → 面试演练 → 生成报告。

- `frontend/`：React + TypeScript + Vite 前端（12 个页面）
- `backend/`：FastAPI + SQLite 后端，负责简历解析、画像抽取、岗位检索与匹配、简历草稿、面试题生成

## 目录

| 路径 | 内容 |
| --- | --- |
| `frontend/` | React + TypeScript + Vite 应用 |
| `backend/` | FastAPI 后端与测试，接口清单见 [backend/README.md](backend/README.md) |
| `DESIGN-SPEC.md` | 设计规范（颜色、字号、间距、动效） |
| `job-hunter-wireframe-v2.html` | 12 块画板线稿，浏览器直接打开 |
| `job-hunter-keyframes.html` | 关键帧 / 交互演示页 |
| `prompts/` | 各画板的画面生成提示词 |
| `jobs/` | 北京技术岗岗位库（JSON → XLSX / Markdown 脚本） |
| `smoke-test.js` | 关键帧页的 DOM 冒烟测试 |
| `流程修改方案.md` | 项目计划书修改方案 |

## 跑前端

```bash
cd frontend
npm install
npm run dev        # http://localhost:5173
npm run build      # 产物在 frontend/dist/
```

## 跑后端

推荐用 uv（仓库带 `uv.lock`）：

```powershell
uv sync
uv run uvicorn backend.app.main:app --reload --reload-dir backend
```

或者 venv：

```powershell
python -m venv .venv
.\.venv\Scripts\python -m pip install -r requirements.txt
.\.venv\Scripts\python -m uvicorn backend.app.main:app --reload
```

打开 http://127.0.0.1:8000/docs。数据库默认 `sqlite:///./ai_job_hunter.db`，首次启动自动建表，并给旧库补齐新增字段。

## 配置

从 `.env.example` 复制成 `.env`：

| 变量 | 用途 |
| --- | --- |
| `DEEPSEEK_API_KEY` | 简历抽取 / 简历草稿需要的模型 Key；不配置时相关接口返回 `503` |
| `DEEPSEEK_MODEL` | 默认 `deepseek-chat` |
| `DEEPSEEK_BASE_URL` | 默认 `https://api.deepseek.com`，可换任意 OpenAI 兼容服务 |
| `DATABASE_URL` | 默认 `sqlite:///./ai_job_hunter.db` |
| `OFFER_CAMPUS_API_KEY` | 岗位采集（Offer先生）用；不配置时 `/jobs/collect` 返回 `503` |
| `OFFER_CAMPUS_API_BASE` | 可覆盖采集接口地址 |

## 前后端联调

前端默认请求 `http://127.0.0.1:8000`，可用 `VITE_API_BASE` 覆盖：

```bash
cd frontend
VITE_API_BASE=http://127.0.0.1:8000 npm run dev
```

- 上传页：选 PDF / DOCX 后调用 `POST /api/v1/profiles/extract/file`，摘要、技能、经历会写进档案。该接口需要 `DEEPSEEK_API_KEY`，未配置时返回 `503`，页面会提示并保留文件信息。
- 岗位页：对每个岗位调用 `POST /api/v1/job-fit`，匹配分、命中项和缺口来自后端。后端未启动时自动回退本地估算，并在页面上方显示提示条。
- GitHub Pages 上没有后端，线上会走本地回退；真正联调请在本地同时起 5173 和 8000。

## 在线演示

前端 GitHub Pages：https://qimahhhh.github.io/jobhunter/

首次部署需要在仓库 **Settings → Pages → Build and deployment → Source** 选择 **GitHub Actions**；之后每次 push 到 `main`，`.github/workflows/deploy.yml` 会自动构建并发布。

生产构建的资源前缀为 `/jobhunter/`，本地 `npm run dev` 仍从根路径 `/` 提供服务。

## 验证

```bash
# 前端
cd frontend
npx tsc --noEmit                    # 类型检查
node scripts/check-css.mjs          # 跨文件选择器覆盖检查
node scripts/check-classes.mjs      # TSX 用到的 class 是否都有定义

cd ..
node smoke-test.js                  # 关键帧页冒烟测试
```

```powershell
# 后端
uv run pytest
```

## 演示数据

档案、问答、面试结果、岗位对比和登录状态保存在浏览器 `localStorage`，key 为 `jobhunter.state.v1`，刷新页面不会丢。

清空演示数据：DevTools → Application → Local Storage 删除该 key，或在控制台执行：

```js
localStorage.removeItem("jobhunter.state.v1");
```

## 不入库的内容

- `node_modules/`、`dist/`、`.vite/`、`.tarballs/`
- `.venv/`、`__pycache__/`、`*.db`、`.env`
- 设计渲染图 `out/v2-frame*.png`、截图 `ui-shots/`（生成物，可重新产出）
