import { useEffect, useMemo, useState } from "react";
import Ticks from "../components/Ticks";
import FlowRail from "../components/FlowRail";
import { useProfile } from "../store";
import { JOBS } from "../jobs";
import { buildInterview } from "../interview";
import type { Route } from "../App";
import type { InterviewAnswer } from "../types";

type Props = {
  go: (r: Route) => void;
  jobId: string;
};

function mmss(s: number) {
  const m = Math.floor(s / 60);
  const r = s % 60;
  return `${String(m).padStart(2, "0")}:${String(r).padStart(2, "0")}`;
}

export default function Interview({ go, jobId }: Props) {
  const { profile, setInterview } = useProfile();
  const job = JOBS.find((j) => j.id === jobId) ?? JOBS[0];

  const questions = useMemo(() => buildInterview(profile, job), [profile, job]);
  const points = useMemo(() => Array.from(new Set(questions.map((q) => q.point))), [questions]);

  const [index, setIndex] = useState(0);
  const [draft, setDraft] = useState("");
  const [answers, setAnswers] = useState<InterviewAnswer[]>([]);
  const [seconds, setSeconds] = useState(0);

  useEffect(() => {
    const t = window.setInterval(() => setSeconds((s) => s + 1), 1000);
    return () => window.clearInterval(t);
  }, []);

  const q = questions[index];
  const finished = index >= questions.length;

  function submit() {
    if (!q) return;
    const next = [...answers, { id: q.id, point: q.point, text: draft.trim() }];
    setAnswers(next);
    setDraft("");
    if (index + 1 >= questions.length) {
      setInterview({ jobId: job.id, answers: next, seconds });
      go("report");
    } else {
      setIndex((i) => i + 1);
    }
  }

  function skip() {
    if (index + 1 >= questions.length) {
      setInterview({ jobId: job.id, answers, seconds });
      go("report");
    } else {
      setIndex((i) => i + 1);
    }
  }

  return (
    <div className="screen">
      <Ticks />
      <div className="gridlines" />

      <header className="topbar">
        <button className="back" onClick={() => go("home")}>
          ← 结束面试
        </button>
      </header>

      <div className="page-head">
        <h1 className="page-title" style={{ fontSize: 24 }}>
          {job.company} · {job.title}
        </h1>
        <p className="page-sub">综合面试 · 模拟模式 · 上限 20 分钟</p>
      </div>

      <div className="iv-body">
        {!finished && q && (
          <div className="iv-card">
            <div className="iv-meta">
              <span>
                <b>第 {index + 1} 题</b> · 共 {questions.length} 题
              </span>
              <span className="iv-time">已用 {mmss(seconds)}</span>
            </div>

            <h3>{q.text}</h3>

            {q.follow && (
              <div className="iv-follow">
                <div className="lb">Follow-up</div>
                <p>{q.follow}</p>
              </div>
            )}

            <textarea
              className="iv-answer"
              value={draft}
              spellCheck={false}
              placeholder="在这里作答，尽量说清楚：为什么这么做、你负责哪一步、最后是什么结果。"
              onChange={(e) => setDraft(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === "Enter" && (e.metaKey || e.ctrlKey)) submit();
              }}
            />
            <div className="iv-hint">⌘ / Ctrl + Enter 提交 · 支持语音（暂未开放）</div>

            <div className="iv-foot">
              <button className="btn" onClick={skip}>
                跳过这题
              </button>
              <button className="btn primary" onClick={submit}>
                {index + 1 >= questions.length ? "提交并生成报告" : "提交回答"}
              </button>
            </div>
          </div>
        )}
      </div>

      <FlowRail
        steps={[
          { label: "选岗位与模式", state: "done" },
          {
            label: "面试进行",
            state: "now",
            sub: `${Math.min(index + 1, questions.length)} / ${questions.length} 题 · ${mmss(seconds)}`,
          },
          { label: "面试报告", state: "next" },
          { label: "复盘重练", state: "next" },
        ]}
      >
        <div className="pts-wrap">
          <div className="cap">考察点 · {Math.min(index, points.length)} / {points.length}</div>
          <ul className="pts">
            {points.map((p, i) => (
              <li key={p} className={i < index ? "on" : ""}>
                <i>{i < index ? "✓" : "·"}</i>
                {p}
              </li>
            ))}
          </ul>
        </div>
      </FlowRail>
      <footer className="meta">
        <span>AI Job Hunter / 2026</span>
        <span>模拟面试 · 不评分</span>
      </footer>
    </div>
  );
}
