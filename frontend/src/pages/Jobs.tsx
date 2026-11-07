import { useEffect, useMemo, useState } from "react";
import Ticks from "../components/Ticks";
import FlowRail from "../components/FlowRail";
import { useProfile } from "../store";
import { JOBS, matchOf, type Job, type Match } from "../jobs";
import { API_BASE, fitJob, type JobFit } from "../api";
import type { Route } from "../App";

type Props = {
  go: (r: Route) => void;
  onPick: (id: string) => void;
};

type ApiState = "loading" | "ok" | "error";

export default function Jobs({ go, onPick }: Props) {
  const { profile, patch, compare } = useProfile();
  const [editing, setEditing] = useState(false);
  const [role, setRole] = useState(profile.target.role ?? "");
  const [city, setCity] = useState(profile.target.city ?? "");
  const [emp, setEmp] = useState<"实习" | "校招" | "社招">(profile.target.employment ?? "实习");

  const [fits, setFits] = useState<Record<string, JobFit>>({});
  const [apiState, setApiState] = useState<ApiState>("loading");
  const [attempt, setAttempt] = useState(0);

  useEffect(() => {
    let cancelled = false;
    setApiState("loading");
    Promise.all(JOBS.map((job) => fitJob(profile, job)))
      .then((results) => {
        if (cancelled) return;
        const next: Record<string, JobFit> = {};
        JOBS.forEach((job, index) => {
          next[job.id] = results[index];
        });
        setFits(next);
        setApiState("ok");
      })
      .catch(() => {
        if (!cancelled) setApiState("error");
      });
    return () => {
      cancelled = true;
    };
  }, [profile, attempt]);

  const rows = useMemo(() => {
    const tier = (verify: Job["verify"]) => (verify === "dead" ? 1 : 0);
    return JOBS.map((job) => {
      const local = matchOf(job, profile);
      const fit = fits[job.id];
      const match: Match = fit
        ? { met: fit.matchPoints, gap: fit.gaps, fail: local.fail, score: fit.score }
        : local;
      return { job, match };
    }).sort(
      (a, b) => tier(a.job.verify) - tier(b.job.verify) || b.match.score - a.match.score
    );
  }, [profile, fits]);

  const verified = rows.filter((r) => r.job.verify === "ok").length;
  const hasTarget = !!(profile.target.city || profile.target.role);

  function save() {
    patch({
      target: {
        role: role.trim() || undefined,
        city: city.trim() || undefined,
        employment: emp as "实习" | "校招" | "社招",
      },
    });
    setEditing(false);
  }

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
        <h1 className="page-title">岗位</h1>
        <p className="page-sub">点进去看它为什么匹配，不只是给一个分。</p>
      </div>

      <div className={`api-bar ${apiState}`}>
        {apiState === "loading" && <span>正在调用后端分析匹配……</span>}
        {apiState === "ok" && <span>匹配分来自后端 {API_BASE} · /api/v1/job-fit</span>}
        {apiState === "error" && (
          <>
            <span>后端未连接（{API_BASE}），当前为本地估算。</span>
            <button onClick={() => setAttempt((n) => n + 1)}>重试</button>
          </>
        )}
      </div>

      <div className="cond">
        <span className="c">{profile.target.role ?? "前端开发"}</span>
        <span className="c">{profile.target.city ?? "不限城市"}</span>
        <span className="c">{profile.target.employment ?? "不限类型"}</span>
        <span className="c">≥ 200 / 天</span>
        <button className="cond-edit" onClick={() => setEditing((v) => !v)}>
          {editing ? "收起" : hasTarget ? "修改条件" : "设定条件"}
        </button>
      </div>

      {editing && (
        <div className="cond-form">
          <label>
            岗位方向
            <input value={role} onChange={(e) => setRole(e.target.value)} placeholder="前端开发" />
          </label>
          <label>
            城市
            <input value={city} onChange={(e) => setCity(e.target.value)} placeholder="上海" />
          </label>
          <label>
            类型
            <select value={emp} onChange={(e) => setEmp(e.target.value as "实习" | "校招" | "社招")}>
              <option value="实习">实习</option>
              <option value="校招">校招</option>
              <option value="社招">社招</option>
            </select>
          </label>
          <button className="btn primary sm" onClick={save}>
            保存
          </button>
        </div>
      )}

      <div className="fbar">
        <span>
          <b>{verified}</b> 已核验
        </span>
        <span>{rows.length} 全部</span>
        <span className="sort">
          <span>
            有效优先 <u>匹配度</u>
          </span>
          <span>最新</span>
        </span>
      </div>

      <div className="jlist">
        {rows.map(({ job, match }) => (
          <div className="jrow" key={job.id} onClick={() => onPick(job.id)}>
            <div className="jmain">
              <h4>
                {job.company} · {job.title}
              </h4>
              <div className="jsub">
                {job.city} · {job.salary} · {job.employment} · {job.education}
              </div>
              <div className="jsrc">
                <i className={`dot ${job.verify}`} />
                {job.verify === "ok" ? "已核验" : job.verify === "dead" ? "来源失效" : "待核验"} ·{" "}
                {job.source} · 采集于 {job.collected}
              </div>
            </div>
            <div className="score">
              <b>{match.score}</b>
              <span>匹配</span>
            </div>
          </div>
        ))}
      </div>

      <div className="pager">
        <span>‹</span>
        <span className="on">1</span>
        <span>2</span>
        <span>3</span>
        <span>…</span>
        <span>7</span>
        <span className="next-page">下一页 ›</span>
      </div>

      {compare.length >= 2 && (
        <div className="cmp-bar">
          <span>已选 {compare.length} 个岗位</span>
          <button className="btn primary" onClick={() => go("compare")}>
            开始对比 →
          </button>
        </div>
      )}

      <FlowRail
        steps={[
          { label: "设定条件", state: "done" },
          { label: "搜索结果", state: "now", sub: `${rows.length} 个 · 第 1 页` },
          { label: "匹配详情", state: "next" },
          { label: "岗位对比", state: "next" },
          { label: "决策", state: "next" },
        ]}
      />
      <footer className="meta">
        <span>AI Job Hunter / 2026</span>
        <span>简历 · 岗位 · 面试</span>
      </footer>
    </div>
  );
}
