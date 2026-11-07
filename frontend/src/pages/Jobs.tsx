import { useState } from "react";
import Ticks from "../components/Ticks";
import FlowRail from "../components/FlowRail";
import { useProfile } from "../store";
import { sortedJobs } from "../jobs";
import type { Route } from "../App";

type Props = {
  go: (r: Route) => void;
  onPick: (id: string) => void;
};

export default function Jobs({ go, onPick }: Props) {
  const { profile, patch, compare } = useProfile();
  const rows = sortedJobs(profile);
  const verified = rows.filter((r) => r.job.verify === "ok").length;

  const [editing, setEditing] = useState(false);
  const [role, setRole] = useState(profile.target.role ?? "");
  const [city, setCity] = useState(profile.target.city ?? "");
  const [emp, setEmp] = useState<"实习" | "校招" | "社招">(profile.target.employment ?? "实习");

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
