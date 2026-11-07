# Job Hunter

AI 求职决策与执行平台的前端原型：上传简历 → 建立档案 → 匹配岗位 → 面试演练 → 生成报告。

## 目录

| 路径 | 内容 |
| --- | --- |
| `frontend/` | React + TypeScript + Vite 应用 |
| `DESIGN-SPEC.md` | 设计规范（颜色、字号、间距、动效） |
| `job-hunter-wireframe-v2.html` | 12 块画板线稿，浏览器直接打开 |
| `job-hunter-keyframes.html` | 关键帧 / 交互演示页 |
| `prompts/` | 各画板的画面生成提示词 |
| `jobs/` | 北京技术岗岗位库（JSON → XLSX / Markdown 脚本） |
| `smoke-test.js` | 关键帧页的 DOM 冒烟测试 |
| `流程修改方案.md` | 项目计划书修改方案 |

## 运行前端

```bash
cd frontend
npm install
npm run dev        # http://localhost:5173
npm run build      # 产物在 frontend/dist/
```

## 在线演示

GitHub Pages：https://qimahhhh.github.io/jobhunter/

首次部署需要在仓库 **Settings → Pages → Build and deployment → Source** 选择 **GitHub Actions**；之后每次 push 到 `main`，`.github/workflows/deploy.yml` 会自动构建并发布。

生产构建的资源前缀为 `/jobhunter/`，本地 `npm run dev` 仍从根路径 `/` 提供服务。

## 验证

```bash
cd frontend
npx tsc --noEmit                    # 类型检查
node scripts/check-css.mjs          # 跨文件选择器覆盖检查
node scripts/check-classes.mjs      # TSX 用到的 class 是否都有定义

cd ..
node smoke-test.js                  # 关键帧页冒烟测试
```

## 演示数据

档案、问答、面试结果、岗位对比和登录状态保存在浏览器 `localStorage`，key 为 `jobhunter.state.v1`，刷新页面不会丢。

清空演示数据：DevTools → Application → Local Storage 删除该 key，或在控制台执行：

```js
localStorage.removeItem("jobhunter.state.v1");
```

## 不入库的内容

- `node_modules/`、`dist/`、`.vite/`、`.tarballs/`
- 设计渲染图 `out/v2-frame*.png`、截图 `ui-shots/`（生成物，可重新产出）
