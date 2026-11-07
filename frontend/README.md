# Job Hunter · 前端

React + TypeScript + Vite。设计规范见仓库根目录 `DESIGN-SPEC.md`，线稿见 `job-hunter-wireframe-v2.html`（12 块画板）。

## 运行

```bash
cd frontend
npm install
npm run dev        # http://localhost:5173
npm run build      # 产物在 dist/
```

> 如果 `npm install` 报 `ECONNRESET`，换成镜像：
> `npm install --registry=https://registry.npmmirror.com`

## 目录

```
src/
├── main.tsx              入口
├── App.tsx               hash 路由（#/intro #/home #/upload …）
├── store.tsx             全局档案（Context + patch）
├── types.ts              类型定义
├── jobs.ts               岗位数据与匹配分规则
├── interview.ts          面试题生成
├── questions.ts          简历问答题目
├── styles/               令牌 / 骨架 / 分页面样式
├── components/           Ticks · Edge · UserBlock · Logo · FlowRail · LoginModal
└── pages/                12 个页面：开场、主页、上传、简历、问答、草稿、
                          岗位列表 / 详情 / 对比、面试、报告、档案
```

## 已完成

- 设计令牌全部落到 CSS 变量，改一处全局生效
- 开场页：标题分级进场（0.7s / 0.8s / 1.25s），点击或 Enter 进入主页
- 主页：三张卡（悬停上移 12px + 交替 ±0.8° + 右下折角展开）、左右边缘圆钮、页脚信息条
- **数据层**：`types.ts` + `store.tsx`（Context + patch），六项完成度由 `checklist()` 统一算
- **上传页**（画板 04）：简历选择 / 替换 / 移除，GitHub 链接与 ZIP 两个入口，主项目标记，经历文本框与字数，右侧完成度实时联动
- **简历页**（画板 05）：生成 / 修改两张卡，没有简历时修改卡降级并指向上传页
- **简历问答**（画板 06）：题量由档案动态生成（加一个项目就多一道题），带「依据」引用、快捷选项 / 自由输入 / 跳过、已确认列表回看
- **岗位列表**（画板 07）：来源 / 核验状态 / 采集时间三件套，按匹配分排序，点行进详情
- **岗位详情**（画板 08）：硬性条件打勾 / 三栏（满足 · 缺证据 · 不满足）+ 右侧分数条，匹配分由 `jobs.ts` 里的规则从 profile 推算（空档案 ~44 分，传了项目和经历 ~92 分）
- **档案页**（画板 11/12）：同一页自动切空态 / 半满态，完成度六格、技能标签、缺口清单（缺口取自匹配分最高那个岗位），面试入口在没目标岗位时禁用
- **目标岗位设定**：岗位页「设定条件」内联表单，写入 `profile.target`，直接影响硬性条件与档案完成度
- **面试进行**（画板 09）：题目从「项目 + 岗位要求」生成，含追问、计时器；作答过程中不评分
- **面试报告**（画板 10）：五维分开给分（分数由回答长度 / 是否含数字推导），薄弱点带重练入口
- **岗位对比**：详情页「加入对比」最多选 4 个，列表底部浮出对比条，对比页并排 6 行维度 + 推荐顺序
- **简历草稿**：A4 预览 + 右侧「待确认」清单，未确认的地方在正文里标虚框，点「去确认」回到问答
- 全局 `prefers-reduced-motion` 降级、`:focus-visible` 焦点环
- **本地持久化**：档案、问答、面试结果、对比和登录状态写入 `localStorage`（key `jobhunter.state.v1`），刷新不丢；清空方式见仓库根 README
- **自动部署**：push 到 `main` 后由 GitHub Actions 构建并发布到 GitHub Pages

## 验证状态

- `tsc --noEmit` **通过**（TypeScript 5.6.3，strict，0 error）
- 依赖已安装（`node_modules/` 已就位）；`vite build` 由 GitHub Actions 在每次 push 时执行，本地沙箱未跑（子进程管道受限）
- 根目录 `smoke-test.js` 对关键帧页做 DOM 冒烟测试，全部通过

## 页面

`#/intro` `#/home` `#/upload` `#/resume` `#/resume-qa` `#/resume-draft`
`#/jobs` `#/job` `#/compare` `#/interview` `#/report` `#/archive`

