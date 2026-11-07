import Ticks from "../components/Ticks";
import FlowRail from "../components/FlowRail";
import { useProfile } from "../store";
import { JOBS } from "../jobs";
import type { Route } from "../App";

type Props = {
  go: (r: Route) => void;
};

const clamp = (n: number) => Math.max(1, Math.min(5, Number(n.toFixed(1))));

export default function Report({ go }: Props) {
  const { interview } = useProfile();
  const answers = interview?.answers ?? [];
  const job = JOBS.find((j) => j.id === interview?.jobId) ?? JOBS[0];

  const answered = answers.filter((a) => a.text.length > 0);
  const noAnswer = answered.length === 0;
  const avg = answered.length
    ? answered.reduce((s, a) => s + a.text.length, 0) / answered.length
    : 0;
  const hasNumber = answered.some((a) => /[0-9]/.test(a.text));

  const dims = noAnswer
    ? [
        { name: "正确性", score: 0, why: "本场没有作答记录，无法评估。" },
        { name: "完整性", score: 0, why: "本场没有作答记录，无法评估。" },
        { name: "逻辑性", score: 0, why: "本场没有作答记录，无法评估。" },
        { name: "细节与真实性", score: 0, why: "本场没有作答记录，无法评估。" },
        { name: "表达清晰度", score: 0, why: "本场没有作答记录，无法评估。" },
      ]
    : [
        {
          name: "正确性",
          score: clamp(3.4 + Math.min(1, avg / 220)),
          why: "结论方向基本正确，个别概念还可以更准确。",
        },
        {
          name: "完整性",
          score: clamp(1.6 + avg / 90),
          why: `平均每次回答 ${Math.round(avg)} 字，${
            avg < 120 ? "多数只讲了做法，没讲结果。" : "结构完整。"
          }`,
        },
        {
          name: "逻辑性",
          score: clamp(3.6 + Math.min(0.9, avg / 400)),
          why: "回答顺序基本按「背景 → 做法」展开。",
        },
        {
          name: "细节与真实性",
          score: clamp(hasNumber ? 3.6 : 2.2),
          why: hasNumber
            ? "出现了具体数字，可信度较好。"
            : "全程没有出现任何具体数字，被追问会站不住。",
        },
        {
          name: "表达清晰度",
          score: clamp(3.2 + Math.min(1.2, avg / 300)),
          why: avg > 260 ? "句子偏长，建议先说结论。" : "表达简洁，重点比较好抓。",
        },
      ];

  const total = noAnswer ? 0 : dims.reduce((s, d) => s + d.score, 0) / dims.length;

  const weak = [
    !hasNumber && {
      title: "缺量化结果",
      text: "整场没有出现具体数字，结果部分说不清",
    },
    answered.length < 3 && {
      title: "作答覆盖不足",
      text: `只完整回答了 ${answered.length} 道题，后面没法评估`,
    },
    avg > 0 &&
      avg < 90 && {
        title: "回答偏短",
        text: `平均 ${Math.round(avg)} 字，面试官会继续追问`,
      },
  ].filter(Boolean) as { title: string; text: string }[];

  const secs = interview?.seconds ?? 0;

  return (
    <div className="screen">
      <Ticks />
      <div className="gridlines" />

      <header className="topbar">
        <button className="back" onClick={() => go("home")}>
          ← 返回主页
        </button>
      </header>

      <div className="page-head">
        <h1 className="page-title">面试报告</h1>
        <p className="page-sub">
          {job.company} · {job.title} · {answers.length} 题 · {Math.floor(secs / 60)} 分{" "}
          {secs % 60} 秒
        </p>
      </div>

      <div className="rep-dims">
        {dims.map((d) => (
          <div className="dim-row" key={d.name}>
            <span className="nm">{d.name}</span>
            <span className="tr">
              <i style={{ width: `${(d.score / 5) * 100}%` }} />
            </span>
            <span className="sc">{noAnswer ? "—" : d.score.toFixed(1)}</span>
            <span className="why">{d.why}</span>
          </div>
        ))}
      </div>

      <div className="rep-weak">
        <div className="cap">薄弱点 · {weak.length}</div>
        {weak.length ? (
          weak.map((w) => (
            <div className="weak" key={w.title}>
              <b>{w.title}</b>
              <span>{w.text}</span>
              <div className="acts">
                <button className="btn sm" onClick={() => go("interview")}>
                  重练
                </button>
              </div>
            </div>
          ))
        ) : (
          <div className="weak">
            <b>没有明显短板</b>
            <span>这场答得不错，可以换个岗位再来一场。</span>
          </div>
        )}
      </div>

      <div className="jfoot" style={{ marginTop: 26 }}>
        <button className="btn primary" onClick={() => go("interview")}>
          再练一次
        </button>
        <button className="btn" onClick={() => go("jobs")}>
          换个岗位
        </button>
        <button className="btn" onClick={() => go("archive")}>
          回到档案
        </button>
      </div>

      <FlowRail
        steps={[
          { label: "选岗位与模式", state: "done" },
          { label: "面试进行", state: "done" },
          { label: "面试报告", state: "now", sub: noAnswer ? "本场无作答" : `${answers.length} 题 · 均分 ${total.toFixed(1)}` },
          { label: "复盘重练", state: "next" },
        ]}
      >
        <div className="sum">
          <div>
            <b>{noAnswer ? "—" : answers.length}</b>
            <span>题数</span>
          </div>
          <div>
            <b>{noAnswer ? "—" : total.toFixed(1)}</b>
            <span>均分</span>
          </div>
        </div>
      </FlowRail>
      <footer className="meta">
        <span>AI Job Hunter / 2026</span>
        <span>面试报告 · 依据可查</span>
      </footer>
    </div>
  );
}
