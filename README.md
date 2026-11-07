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

## 验证

```bash
cd frontend
npx tsc --noEmit                    # 类型检查
node scripts/check-css.mjs          # 跨文件选择器覆盖检查
node scripts/check-classes.mjs      # TSX 用到的 class 是否都有定义

cd ..
node smoke-test.js                  # 关键帧页冒烟测试
```

## 不入库的内容

- `node_modules/`、`dist/`、`.vite/`、`.tarballs/`
- 设计渲染图 `out/v2-frame*.png`、截图 `ui-shots/`（生成物，可重新产出）
