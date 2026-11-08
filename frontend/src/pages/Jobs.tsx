import { useEffect, useMemo, useState } from "react";
import Top from "../components/Top";
import Band from "../components/Band";
import { useProfile } from "../store";
import { JOBS, matchOf, type Job, type Match } from "../jobs";
import { API_BASE, fitJob, type JobFit } from "../api";
import type { Route } from "../App";

type Props = {
  go: (r: Route) => void;
  onPick: (id: string) => void;
};

type ApiState = "loading" | "ok" | "error";

const VERIFY_TEXT: Record<Job["verify"], string> = {
  ok: "已核验 · 仍在招",
  pending: "待核验 · 未回访",
  dead: "来源失效 · 已关闭",
};

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
      return { job, match, local };
    }).sort(
      // 顺序只用本地匹配分算，后端结果回来时只换分数、不换位置，避免首帧跳动
      (a, b) =>
        tier(a.job.verify) - tier(b.job.verify) ||
        b.local.score - a.local.score ||
        a.job.id.localeCompare(b.job.id)
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
    <div className="shell" id="main">
      <Top
        onHome={() => go("home")}
        back={{ label: "返回主页", onClick: () => go("home") }}
      />

      <main className="page">
        <div className="eyebrow">B 区 · 岗位</div>
        <h1 className="h1 mt-16">哪个值得投？</h1>
        <p className="lead">
          点进去看它为什么匹配，不只是给一个分。失效的岗位会留在名录里，划掉，但不抹掉。
        </p>

        <div className="row between wrap mt-24" style={{ gap: 12 }}>
          <div className="row wrap" style={{ gap: 8 }}>
            <span className="tag">{profile.target.role ?? "前端开发"}</span>
            <span className="tag">{profile.target.city ?? "不限城市"}</span>
            <span className="tag">{profile.target.employment ?? "不限类型"}</span>
            <span className="tag mute">≥ 200 / 天</span>
          </div>
          <button
            className="pill sm"
            type="button"
            onClick={() => setEditing((v) => !v)}
          >
            {editing ? "收起" : hasTarget ? "修改条件" : "设定条件"}
          </button>
        </div>

        {editing && (
          <div className="panel mt-16">
            <div className="row wrap" style={{ gap: 16, alignItems: "flex-end" }}>
              <label className="field" style={{ flex: "1 1 200px", marginTop: 0 }}>
                <span>岗位方向</span>
                <input value={role} onChange={(e) => setRole(e.target.value)} placeholder="前端开发" />
              </label>
              <label className="field" style={{ flex: "1 1 160px", marginTop: 0 }}>
                <span>城市</span>
                <input value={city} onChange={(e) => setCity(e.target.value)} placeholder="上海" />
              </label>
              <label className="field" style={{ flex: "1 1 140px", marginTop: 0 }}>
                <span>类型</span>
                <select value={emp} onChange={(e) => setEmp(e.target.value as "实习" | "校招" | "社招")}>
                  <option value="实习">实习</option>
                  <option value="校招">校招</option>
                  <option value="社招">社招</option>
                </select>
              </label>
              <button className="pill solid" onClick={save} type="button">
                保存
              </button>
            </div>
          </div>
        )}

        <div className="row between wrap mt-24" style={{ gap: 12 }}>
          <span className="fs-13 muted">
            <b className="mono" style={{ fontSize: 18, color: "var(--ink)" }}>{verified}</b> 已核验 /{" "}
            {rows.length} 全部 · 有效优先
          </span>
          <span className="fs-11 muted" style={{ letterSpacing: ".12em" }}>
            {apiState === "loading" && "正在向后端核对匹配……"}
            {apiState === "ok" && `匹配分来自后端 ${API_BASE}`}
            {apiState === "error" && `后端未连接（${API_BASE}），当前为本地估算`}
          </span>
          {apiState === "error" && (
            <button className="pill sm" type="button" onClick={() => setAttempt((n) => n + 1)}>
              重试
            </button>
          )}
        </div>

        <div className="jlist mt-16">
          {rows.map(({ job, match }) => (
            <button
              key={job.id}
              className={job.verify === "dead" ? "jrow dead" : "jrow"}
              onClick={() => onPick(job.id)}
              type="button"
            >
              <span className="j-main">
                <span className="j-title">
                  {job.company} · {job.title}
                </span>
                <span className="j-sub">
                  {job.city} · {job.salary} · {job.employment} · {job.education}
                </span>
                <span className="j-src">
                  <i
                    className={
                      job.verify === "ok" ? "dot" : job.verify === "dead" ? "dot dead" : "dot hollow"
                    }
                  />
                  {VERIFY_TEXT[job.verify]} · {job.source} · 采集于 {job.collected}
                </span>
              </span>
              <span className="j-score num">{match.score}</span>
              <span className="j-arrow" aria-hidden="true">
                →
              </span>
            </button>
          ))}
        </div>

        <p className="small mt-24">
          「缺证据」不等于「不满足」：前者是你没写，后者是岗位不让。点进详情分得清。
        </p>
      </main>

      <Band
        step={2}
        total={4}
        label={`岗位 · 已核验 ${verified} 个`}
        action={
          compare.length >= 2
            ? { label: `去对比（${compare.length}）`, onClick: () => go("compare") }
            : { label: "先看一个岗位", onClick: () => onPick(rows[0].job.id) }
        }
      />
    </div>
  );
}
