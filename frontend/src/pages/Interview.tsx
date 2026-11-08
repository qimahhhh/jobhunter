import { useEffect, useMemo, useState } from "react";
import Top from "../components/Top";
import Band from "../components/Band";
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
    <div className="shell" id="main">
      <Top
        onHome={() => go("home")}
        back={{ label: "结束面试", onClick: () => go("home") }}
      />

      <main className="page">
        <div className="eyebrow">
          {job.company} · {job.title}
        </div>

        <div
          className="row between wrap mt-24"
          style={{ gap: 32, alignItems: "flex-end" }}
        >
          <div>
            <div className="eyebrow">
              第 {index + 1} 题 · 共 {questions.length} 题
            </div>
            <div
              className="num mt-8"
              style={{ fontSize: "clamp(64px, 9vw, 120px)", lineHeight: 0.8 }}
            >
              {String(index + 1).padStart(2, "0")}
              <span className="muted" style={{ fontSize: "0.32em", letterSpacing: 0 }}>
                {" "}
                / {String(questions.length).padStart(2, "0")}
              </span>
            </div>
          </div>
          <div style={{ textAlign: "right" }}>
            <div className="eyebrow">已用时间</div>
            <div
              className="num mt-8"
              style={{ fontSize: "clamp(44px, 6vw, 80px)", lineHeight: 0.85 }}
            >
              {mmss(seconds)}
            </div>
          </div>
        </div>

        <div className="row between wrap mt-16" style={{ gap: 12 }}>
          <span className="small">综合面试 · 模拟模式 · 上限 20 分钟</span>
          <span className="small">
            考察点 · {Math.min(index, points.length)} / {points.length}
          </span>
        </div>

        {!finished && q && (
          <>
            <h1 className="h1 mt-48">{q.text}</h1>

            {q.follow && (
              <div className="row wrap mt-24" style={{ gap: 12, alignItems: "baseline" }}>
                <span className="tag">Follow-up</span>
                <span className="small" style={{ maxWidth: "34em" }}>
                  {q.follow}
                </span>
              </div>
            )}

            <textarea
              className="mt-32"
              style={{ minHeight: 260 }}
              value={draft}
              spellCheck={false}
              placeholder="在这里作答，尽量说清楚：为什么这么做、你负责哪一步、最后是什么结果。"
              onChange={(e) => setDraft(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === "Enter" && (e.metaKey || e.ctrlKey)) submit();
              }}
            />
            <div className="fs-11 muted mt-8">⌘ / Ctrl + Enter 提交 · 支持语音（暂未开放）</div>

            <div className="row wrap mt-24" style={{ gap: 10 }}>
              {index + 1 < questions.length && (
                <button className="pill" onClick={skip} type="button">
                  跳过这题
                </button>
              )}
              <button className="pill solid" onClick={submit} type="button">
                {index + 1 >= questions.length ? "提交并生成报告" : "提交回答"}
              </button>
            </div>

            <div className="row wrap mt-48" style={{ gap: 6 }}>
              {points.map((p, i) => (
                <span key={p} className={i < index ? "tag" : "tag mute"}>
                  {i < index ? "✓" : "·"} {p}
                </span>
              ))}
            </div>
          </>
        )}
      </main>

      <Band
        step={3}
        total={4}
        label={`面试进行 · ${Math.min(index + 1, questions.length)} / ${questions.length} 题`}
      />
    </div>
  );
}
