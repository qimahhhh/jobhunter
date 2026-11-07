import { useEffect, useState } from "react";
import Ticks from "../components/Ticks";
import FlowRail from "../components/FlowRail";
import { useProfile } from "../store";
import { JOBS, matchOf } from "../jobs";
import { API_BASE, fitJob, type JobFit } from "../api";
import type { Route } from "../App";

type Props = {
  go: (r: Route) => void;
  jobId: string;
};

type Status = "loading" | "ok" | "error";

export default function JobDetail({ go, jobId }: Props) {
  const { profile, compare, toggleCompare } = useProfile();
  const job = JOBS.find((j) => j.id === jobId) ?? JOBS[0];
  const [fit, setFit] = useState<JobFit | null>(null);
  const [status, setStatus] = useState<Status>("loading");
  const [attempt, setAttempt] = useState(0);

  useEffect(() => {
    let cancelled = false;
    setStatus("loading");
    setFit(null);
    fitJob(profile, job)
      .then((result) => {
        if (cancelled) return;
        setFit(result);
        setStatus("ok");
      })
      .catch(() => {
        if (!cancelled) setStatus("error");
      });
    return () => {
      cancelled = true;
    };
  }, [profile, job, attempt]);

  const local = matchOf(job, profile);
  // 后端的 match_points 只返回前 5 个关键词，硬性条件可能被截掉；
  // 这里把本地能确定的硬性项并回来，保证打勾和列表不矛盾。
  const met = fit
    ? Array.from(
        new Set([
          ...job.reqs
            .filter((r) => r.type === "hard" && local.met.includes(r.label))
            .map((r) => r.label),
          ...fit.matchPoints,
        ])
      )
    : local.met;
  const m = {
    met,
    gap: fit?.gaps ?? local.gap,
    fail: local.fail,
    score: fit?.score ?? local.score,
  };
  const inCompare = compare.includes(job.id);

  const skills = profile.projects.length ? 82 : 46;
  const proj = profile.projects.length ? 71 : 34;
  const exp = profile.stories.trim() ? 64 : 28;

  const softMet = m.met.filter(
    (label) => !job.reqs.some((r) => r.label === label && r.type === "hard")
  );

  return (
    <div className="screen">
      <Ticks />
      <div className="gridlines" />

      <header className="topbar">
        <button className="back" onClick={() => go("jobs")}>
          ← 返回结果列表
        </button>
      </header>

      <div className="jhead">
        <h2>
          {job.company} · {job.title}
        </h2>
        <div className="jhead-sub">
          {job.city} · {job.salary} · {job.employment} · <b>{job.source}</b> ·{" "}
          <i className={`dot ${job.verify}`} />{" "}
          {job.verify === "ok" ? "已核验" : job.verify === "dead" ? "来源失效" : "待核验"} · 采集于{" "}
          {job.collected}
        </div>
        <div className="fitline">
          <b>{m.score}</b>
          <span>AI 匹配</span>
          <em className={status === "error" ? "err" : ""}>
            {status === "loading"
              ? "后端分析中…"
              : status === "error"
                ? `后端未连接（${API_BASE}），本地估算`
                : "来自后端 /api/v1/job-fit"}
          </em>
          {status === "error" && (
            <button className="btn sm" onClick={() => setAttempt((n) => n + 1)}>
              重试
            </button>
          )}
        </div>
      </div>

      <div className="krow">
        {job.reqs
          .filter((r) => r.type === "hard")
          .map((r) => (
            <div className={m.met.includes(r.label) ? "k ok" : "k no"} key={r.label}>
              <i>{m.met.includes(r.label) ? "✓" : "✕"}</i>
              {r.label}
            </div>
          ))}
      </div>

      <div className="cols">
        <div className="col">
          <h5>满足 · {m.met.length}</h5>
          <ul>
            {m.met.map((x) => (
              <li key={x}>
                <em>✓</em>
                {x}
              </li>
            ))}
          </ul>
        </div>
        <div className="col miss">
          <h5>缺证据 · {m.gap.length}</h5>
          <ul>
            {m.gap.length ? (
              m.gap.map((x) => (
                <li key={x}>
                  <em>?</em>
                  {x}（档案里没写）
                </li>
              ))
            ) : (
              <li>
                <em>·</em>没有缺口
              </li>
            )}
          </ul>
        </div>
        <div className="col miss">
          <h5>不满足 · {m.fail.length}</h5>
          <ul>
            {m.fail.length ? (
              m.fail.map((x) => (
                <li key={x}>
                  <em>✕</em>
                  {x}
                </li>
              ))
            ) : (
              <li>
                <em>·</em>硬性条件全部满足
              </li>
            )}
          </ul>
        </div>
      </div>

      {fit && (
        <div className="fit-note">
          <div className="cap">后端分析 · 置信度 {Math.round(fit.confidence * 100)}%</div>
          <p>
            命中 {fit.matchPoints.length} 个关键词，缺口 {fit.gaps.length} 个。
          </p>
          <p>
            {fit.gaps.length
              ? `优先补证据：${fit.gaps.join("、")}`
              : "岗位关键词已全覆盖，接下来核对项目深度和结果。"}
          </p>
        </div>
      )}

      <div className="next">
        <div className="cap">下一步</div>
        <ul>
          <li>
            <b>简历强调</b>
            {fit?.matchPoints.length
              ? fit.matchPoints.slice(0, 3).join("、")
              : softMet.length
                ? softMet.slice(0, 3).join("、")
                : "先把项目经历和技能证据补上"}
          </li>
          <li>
            <b>面试准备</b>
            大概率问：虚拟列表、首屏优化、组件抽象
          </li>
          <li>
            <b>去补充</b>
            {m.gap.length ? m.gap.slice(0, 2).join("、") : "暂时没有明显缺口"}
          </li>
        </ul>
      </div>

      <div className="jfoot">
        <button className="btn primary" onClick={() => go("resume")}>
          生成定制简历
        </button>
        <button className={inCompare ? "btn on" : "btn"} onClick={() => toggleCompare(job.id)}>
          {inCompare ? "已加入对比" : "加入对比"}
        </button>
        {compare.length >= 2 && (
          <button className="btn" onClick={() => go("compare")}>
            去对比（{compare.length}）
          </button>
        )}
        <button className="btn" onClick={() => go("jobs")}>
          不考虑
        </button>
      </div>

      <FlowRail
        steps={[
          { label: "设定条件", state: "done" },
          { label: "搜索结果", state: "done" },
          { label: "匹配详情", state: "now", sub: "可解释的匹配" },
          { label: "岗位对比", state: "next" },
          { label: "决策", state: "next" },
        ]}
      >
        <div className="bars">
          <div className="bar">
            <div className="lb">
              <span>技能</span>
              <span>{skills}</span>
            </div>
            <div className="tr">
              <i style={{ width: `${skills}%` }} />
            </div>
          </div>
          <div className="bar">
            <div className="lb">
              <span>项目</span>
              <span>{proj}</span>
            </div>
            <div className="tr">
              <i style={{ width: `${proj}%` }} />
            </div>
          </div>
          <div className="bar">
            <div className="lb">
              <span>经历</span>
              <span>{exp}</span>
            </div>
            <div className="tr">
              <i style={{ width: `${exp}%` }} />
            </div>
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
