import { useEffect, useState } from "react";
import Top from "../components/Top";
import Band from "../components/Band";
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

  const softMet = m.met.filter(
    (label) => !job.reqs.some((r) => r.label === label && r.type === "hard")
  );

  const verdict = m.fail.length
    ? "硬性条件没过，先看差在哪"
    : m.gap.length
      ? "硬性条件全过，还缺一条证据"
      : "全部对上，可以直接投";

  const verifiedText =
    job.verify === "ok" ? "已核验 · 仍在招" : job.verify === "dead" ? "来源失效 · 已关闭" : "待核验 · 未回访";

  return (
    <div className="shell" id="main">
      <Top
        onHome={() => go("home")}
        back={{ label: "返回名录", onClick: () => go("jobs") }}
      />

      <main className="page">
        <div className="row between wrap" style={{ gap: 16 }}>
          <div>
            <div className="eyebrow">
              {job.company} · {job.title}
            </div>
            <h1 className="h1 mt-16">{job.company} · {job.title}</h1>
          </div>
          <div className="row" style={{ gap: 8, alignSelf: "flex-end" }}>
            <i
              className={
                job.verify === "ok" ? "dot" : job.verify === "dead" ? "dot dead" : "dot hollow"
              }
            />
            <span className="fs-13 muted">{verifiedText}</span>
          </div>
        </div>

        <p className="lead">
          {job.city} · {job.salary} · {job.employment} · {job.source} · 采集于 {job.collected}
        </p>

        <div className="verdict mt-32">
          <div className="v-num num">{m.score}</div>
          <div className="v-txt">
            <div className="eyebrow">匹配</div>
            <p className="mt-8">{verdict}</p>
            <div className="fit-status fs-13 mt-8">
              {status === "loading" && "后端分析中……（当前为本地估算）"}
              {status === "ok" && "来自后端 /api/v1/job-fit"}
              {status === "error" && `后端未连接（${API_BASE}），本地估算`}
            </div>
          </div>
          {status === "error" && (
            <button
              className="pill sm"
              style={{ marginLeft: "auto" }}
              type="button"
              onClick={() => setAttempt((n) => n + 1)}
            >
              重试
            </button>
          )}
        </div>

        <div className="reqs mt-24">
          {job.reqs
            .filter((r) => r.type === "hard")
            .map((r) => {
              const ok = m.met.includes(r.label);
              return (
                <span className={ok ? "tag" : "tag red"} key={r.label}>
                  {ok ? "✓" : "✕"} {r.label}
                </span>
              );
            })}
        </div>

        <div className="grid3 mt-32">
          <div className="col-list">
            <h4>满足 · {m.met.length}</h4>
            <ul>
              {m.met.map((x) => (
                <li key={x}>
                  <em>✓</em>
                  {x}
                </li>
              ))}
              {!m.met.length && (
                <li>
                  <em>·</em>还没有可用的证据
                </li>
              )}
            </ul>
          </div>
          <div className="col-list">
            <h4>缺证据 · {m.gap.length}</h4>
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
          <div className="col-list">
            <h4>不满足 · {m.fail.length}</h4>
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
          <div className="panel mt-24">
            <div className="eyebrow">后端分析 · 置信度 {Math.round(fit.confidence * 100)}%</div>
            <p className="mt-8" style={{ fontSize: 15 }}>
              命中 {fit.matchPoints.length} 个关键词，缺口 {fit.gaps.length} 个。
            </p>
            <p className="small mt-8">
              {fit.gaps.length
                ? `优先补证据：${fit.gaps.join("、")}`
                : "岗位关键词已全覆盖，接下来核对项目深度和结果。"}
            </p>
          </div>
        )}

        <div className="grid3 mt-32">
          <div className="col-list">
            <h4>下一步 · 简历强调</h4>
            <p style={{ fontSize: 14 }}>
              {fit?.matchPoints.length
                ? fit.matchPoints.slice(0, 3).join("、")
                : softMet.length
                  ? softMet.slice(0, 3).join("、")
                  : "先把项目经历和技能证据补上"}
            </p>
          </div>
          <div className="col-list">
            <h4>下一步 · 面试准备</h4>
            <p style={{ fontSize: 14 }}>大概率问：虚拟列表、首屏优化、组件抽象</p>
          </div>
          <div className="col-list">
            <h4>下一步 · 去补充</h4>
            <p style={{ fontSize: 14 }}>
              {m.gap.length ? m.gap.slice(0, 2).join("、") : "暂时没有明显缺口"}
            </p>
          </div>
        </div>

        <div className="row wrap mt-32" style={{ gap: 10 }}>
          <button className="pill solid" onClick={() => go("resume")} type="button">
            生成定制简历
          </button>
          <button className="pill" onClick={() => toggleCompare(job.id)} type="button">
            {inCompare ? "已加入对比" : "加入对比"}
          </button>
          <button className="pill" onClick={() => go("interview")} type="button">
            面这个
          </button>
          <button className="pill" onClick={() => go("jobs")} type="button">
            不考虑
          </button>
        </div>
      </main>

      <Band
        step={2}
        total={4}
        label={`只看这一个 · ${job.company}`}
        action={{ label: "去模拟面试 →", onClick: () => go("interview") }}
      />
    </div>
  );
}
