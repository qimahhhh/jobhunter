import Top from "../components/Top";
import Band from "../components/Band";
import { useProfile } from "../store";
import { JOBS } from "../jobs";
import type { Route } from "../App";

type Props = {
  go: (r: Route) => void;
};

const clamp = (n: number) => Math.max(1, Math.min(5, Number(n.toFixed(1))));

export default function Report({ go }: Props) {
  const { interview, unlocked } = useProfile();
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
    <div className="shell" id="main">
      <Top
        onHome={() => go("home")}
        back={{ label: "返回主页", onClick: () => go("home") }}
      />

      <main className="page">
        <div className="eyebrow">
          {job.company} · {job.title}
        </div>
        <h1 className="h1 mt-16">面试报告</h1>
        <p className="lead">
          {answers.length} 题 · {Math.floor(secs / 60)} 分 {secs % 60} 秒
        </p>

        <div className="verdict mt-32">
          <div className="v-num num">{noAnswer ? "—" : total.toFixed(1)}</div>
          <div className="v-txt">
            <div className="eyebrow">均分 / 5</div>
            <p className="mt-8">
              {noAnswer
                ? "本场没有作答记录，无法评估。"
                : `${answers.length} 题 · 均分 ${total.toFixed(1)}`}
            </p>
          </div>
        </div>

        <div className="mt-32" style={{ borderTop: "1.5px solid var(--ink)" }}>
          {dims.map((d) => (
            <div
              key={d.name}
              style={{ padding: "16px 0", borderBottom: "1px solid var(--line)" }}
            >
              <div
                style={{
                  display: "grid",
                  gridTemplateColumns: "minmax(96px, 160px) minmax(60px, 1fr) 64px",
                  alignItems: "center",
                  gap: 20,
                }}
              >
                <span className="h3" style={{ fontSize: 15 }}>
                  {d.name}
                </span>
                <span
                  aria-hidden="true"
                  style={{
                    display: "block",
                    height: 1,
                    background: "var(--hair)",
                    position: "relative",
                  }}
                >
                  <i
                    style={{
                      position: "absolute",
                      left: 0,
                      top: -1.5,
                      display: "block",
                      height: 4,
                      width: noAnswer ? 0 : `${(d.score / 5) * 100}%`,
                      background: "var(--ink)",
                    }}
                  />
                </span>
                <span className="num" style={{ textAlign: "right", fontSize: 22 }}>
                  {noAnswer ? "—" : d.score.toFixed(1)}
                </span>
              </div>
              {unlocked && (
                <p className="small" style={{ marginTop: 6 }}>
                  {d.why}
                </p>
              )}
            </div>
          ))}
        </div>

        {unlocked ? (
          <>
            <div className="mt-48">
              <div className="row between wrap" style={{ gap: 12 }}>
                <h2 className="h2">薄弱点</h2>
                <span className="eyebrow">{weak.length} 项</span>
              </div>
              <div className="mt-16" style={{ borderTop: "1.5px solid var(--ink)" }}>
                {weak.length ? (
                  weak.map((w) => (
                    <div
                      key={w.title}
                      className="row between wrap"
                      style={{
                        gap: 20,
                        padding: "18px 0",
                        borderBottom: "1px solid var(--line)",
                      }}
                    >
                      <div>
                        <div className="h3">{w.title}</div>
                        <div className="small">{w.text}</div>
                      </div>
                      <button
                        className="pill sm"
                        onClick={() => go("interview")}
                        type="button"
                      >
                        重练
                      </button>
                    </div>
                  ))
                ) : (
                  <div
                    className="row between wrap"
                    style={{
                      gap: 20,
                      padding: "18px 0",
                      borderBottom: "1px solid var(--line)",
                    }}
                  >
                    <div>
                      <div className="h3">没有明显短板</div>
                      <div className="small">这场答得不错，可以换个岗位再来一场。</div>
                    </div>
                  </div>
                )}
              </div>
            </div>

            <div className="row wrap mt-32" style={{ gap: 10 }}>
              <button className="pill solid" onClick={() => go("interview")} type="button">
                再练一次
              </button>
              <button className="pill" onClick={() => go("jobs")} type="button">
                换个岗位
              </button>
              <button className="pill" onClick={() => go("archive")} type="button">
                回到档案
              </button>
            </div>
          </>
        ) : (
          <div className="panel y mt-32">
            <div className="eyebrow">完整报告 · 未解锁</div>
            <p className="h2 mt-8">五维评分已经给出，改法还在后面。</p>
            <p className="small mt-8">
              完整报告包含：每项评分的依据与改法、薄弱点清单、每道题的追问记录，以及可导出的一页总结。
            </p>
            <button className="pill solid mt-24" onClick={() => go("purchase")} type="button">
              购买服务解锁全部 →
            </button>
          </div>
        )}
      </main>

      <Band
        step={4}
        total={4}
        label={`面试报告 · ${noAnswer ? "本场无作答" : `均分 ${total.toFixed(1)}`}`}
        action={
          unlocked
            ? { label: "回到档案", onClick: () => go("archive") }
            : { label: "解锁完整报告", onClick: () => go("purchase") }
        }
      />
    </div>
  );
}
