# Product

<!-- impeccable:product-schema 1 -->

## Platform

web

## Users

大学生（本科 / 研究生），处在秋招或春招的求职期，独自使用，没有人陪跑。典型情形：投了两周没回音，开始怀疑简历；或者拿到几个岗位，说不清哪个更值得投。他们要的不是更多职位，是「我为什么该投这个、我还缺什么」的答案。

使用环境：宿舍或图书馆的笔记本电脑，浏览器同时开着招聘网站、牛客和学校就业网；也会用手机看一眼进度，但真正操作在桌面。

## Product Purpose

把简历、岗位、模拟面试连成一条决策线：解析真实经历 → 判断岗位是否仍在招 → 说明匹配依据 → 面试演练 → 出报告。成功不是"拿到一个匹配分"，而是用户能自己讲清楚"为什么投这个、差在哪、下一轮改什么"。

## Positioning

每个结论都能展开看依据：匹配分必须能落到具体命中项与缺口，岗位必须标出核验状态（已核验 / 待核验 / 来源失效）。邻家产品能给一个总分，给不出"这个分由哪几条经历支撑"。

## Operating Context

- 求职季高频、短时：一晚上过十几个岗位，一次只看几分钟。
- 多窗口作业：JD 从招聘网站复制、简历从本地 PDF 上传、面经在另一个标签页。
- 产物会离开这个界面：报告要能截图 / 导出给同学、学长或老师看。
- 使用痕迹：简历 PDF / DOCX、岗位 JD 文本、模拟面试的逐轮问答记录、最终报告。

## Capabilities and Constraints

- 前端 React 18 + TypeScript + Vite，12 条 hash 路由：intro / home / upload / resume / resume-qa / resume-draft / jobs / job / interview / report / compare / archive。
- 演示态存 `localStorage`，key `jobhunter.state.v1`；刷新不丢，清空靠删 key。
- 后端 FastAPI：`POST /api/v1/profiles/extract/file`、`/api/v1/job-fit` 等；未连后端时前端回退本地估算并在页面上方显示提示条，这个降级路径是功能的一部分。
- 未配置 `DEEPSEEK_API_KEY` 时上传解析返回 503，页面必须提示并保留已选文件信息。
- 岗位库是本地 JSON（北京技术岗），核验状态、来源、采集日期是展示的一部分。
- 前端部署 GitHub Pages，生产资源前缀 `/jobhunter/`；本地 dev 从 `/` 起。
- 中文界面，无多语言需求。

## Brand Commitments

- 产品名「Job Hunter」保留，不改名。
- 视觉世界不作承诺：用户明确放开，上一版 `DESIGN-SPEC.md`（黑白 + 单蓝、超大字、等宽小标、四角角标、纸折角卡片）是历史记录，不是约束。

## Evidence on Hand

- 已实现的界面：12 条路由全部有代码，`frontend/src/`。
- `DESIGN-SPEC.md`（v1.0 视觉规范）、`job-hunter-wireframe-v2.html`（12 块画板线稿）、`job-hunter-keyframes.html`（关键帧演示）。
- 旧截图：`frontend/shots/`。
- 无真实用户评价、无使用数据、无客户案例、无真实岗位数据授权 —— 这些不得编造，也不得在界面上伪造社会证明。

## Product Principles

1. 依据先于结论：任何分数旁边都能找到它由什么算出来。
2. 一屏一个决定：每个页面只回答一个问题，不让用户同时做两件事。
3. 缺什么就说什么：后端没连、岗位失效、经历不够，都直接讲，不用委婉语掩盖。
4. 产物要能带走：报告与对比结果必须能截图 / 打印 / 交给别人看。

## Accessibility & Inclusion

- 键盘全程可达，`:focus-visible` 有明确焦点环。
- 正文对比度 ≥ 4.5:1，非文本图形 ≥ 3:1。
- `prefers-reduced-motion: reduce` 时所有动效静止且内容完整可见。
