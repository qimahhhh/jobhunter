import { useState } from "react";
import Ticks from "../components/Ticks";
import FlowRail from "../components/FlowRail";
import { useProfile } from "../store";
import { buildQuestions } from "../questions";
import type { Route } from "../App";

export default function ResumeQA({ go }: { go: (r: Route) => void }) {
  const { profile, patch } = useProfile();
  const questions = buildQuestions(profile);

  const [index, setIndex] = useState(() => {
    // 回到本页时从第一道没答过的题开始，而不是永远从第 1 题重来
    const next = questions.findIndex((q) => !profile.answers[q.id]);
    return next === -1 ? questions.length : next;
  });
  const [free, setFree] = useState("");

  const answered = Object.keys(profile.answers).length;
  const finished = index >= questions.length;
  const q = questions[index];

  function answer(value: string) {
    if (!q) return;
    patch({ answers: { ...profile.answers, [q.id]: value } });
    setFree("");
    setIndex((i) => i + 1);
  }

  return (
    <div className="screen">
      <Ticks />
      <div className="gridlines" />

      <header className="topbar">
        <button className="back" onClick={() => go("resume")}>
          ← 返回上一步
        </button>
      </header>

      <div className="page-head">
        <h1 className="page-title">确认信息</h1>
        <p className="page-sub">
          {finished
            ? `问完了 ${answered} 个问题，剩下的交给生成。`
            : "只问档案里说不清的地方，答完一条就少一个疑点。"}
        </p>
      </div>

      <div className="qa-main">
        {finished ? (
          <div className="q done-card">
            <div className="q-top">
              <span className="cnt">问答完成</span>
            </div>
            <h3>档案里能问的都问完了。</h3>
            <p className="q-basis">
              <b>接下来</b>：用这些确认过的事实生成草稿；没答的地方会在简历里标成「待确认」，不会替你编。
            </p>
            <div className="q-foot">
              <button className="q-esc" onClick={() => go("resume")}>
                回到上一步
              </button>
              <button className="btn primary" onClick={() => go("resume-draft")}>
                生成草稿
              </button>
            </div>
          </div>
        ) : (
          <div className="q">
            <div className="q-top">
              <span className="cnt">
                问题 {String(index + 1).padStart(2, "0")} / {String(questions.length).padStart(2, "0")}
              </span>
              <button className="btn sm" onClick={() => setIndex((i) => i + 1)}>
                跳过
              </button>
            </div>

            <h3>{q.title}</h3>

            <div className="q-basis">
              <b>依据</b>：{q.basis}
            </div>

            <div className="q-opts">
              {q.options.map((o) => (
                <button key={o} onClick={() => answer(o)}>
                  {o}
                </button>
              ))}
            </div>

            <div className="q-free">
              <input
                value={free}
                placeholder={q.placeholder}
                onChange={(e) => setFree(e.target.value)}
                onKeyDown={(e) => {
                  if (e.key === "Enter" && free.trim()) answer(free.trim());
                }}
              />
            </div>

            <div className="q-foot">
              <button className="q-esc" onClick={() => setIndex(questions.length)}>
                就这些，用现有信息继续 →
              </button>
              <button
                className="btn primary"
                disabled={!free.trim()}
                onClick={() => answer(free.trim())}
              >
                确认并继续
              </button>
            </div>
          </div>
        )}

        {answered > 0 && (
          <div className="done-list">
            <div className="cap">已确认 {answered} 条</div>
            <ul>
              {Object.entries(profile.answers).map(([id, value]) => {
                const hit = questions.find((x) => x.id === id);
                return (
                  <li key={id}>
                    <b>{hit?.tag ?? "档案"}</b>
                    <span>{value}</span>
                  </li>
                );
              })}
            </ul>
          </div>
        )}
      </div>

      <FlowRail
        steps={[
          { label: "选择方式", state: "done" },
          { label: "读取档案", state: "done" },
          {
            label: "确认信息",
            state: "now",
            sub: finished
              ? "已问完"
              : `${Math.min(index + 1, questions.length)} / ${questions.length} · 还剩 ${Math.max(
                  questions.length - index - 1,
                  0
                )}`,
          },
          { label: "生成草稿", state: "next" },
          { label: "检查与导出", state: "next" },
        ]}
      >
        <div className="sum">
          <div>
            <b>{answered}</b>
            <span>已确认</span>
          </div>
          <div>
            <b>{Math.max(questions.length - index, 0)}</b>
            <span>还差</span>
          </div>
        </div>
      </FlowRail>
      <footer className="meta">
        <span>AI Job Hunter / 2026</span>
        <span>简历 · 岗位 · 面试</span>
      </footer>
    </div>
  );
}
