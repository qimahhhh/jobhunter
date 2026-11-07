import Ticks from "../components/Ticks";
import FlowRail from "../components/FlowRail";
import { useProfile } from "../store";
import { JOBS, matchOf } from "../jobs";
import type { Route } from "../App";

type Props = {
  go: (r: Route) => void;
};

export default function Compare({ go }: Props) {
  const { profile, compare, toggleCompare } = useProfile();

  const picked = compare
    .map((id) => JOBS.find((j) => j.id === id))
    .filter((j): j is NonNullable<typeof j> => !!j)
    .map((job) => ({ job, m: matchOf(job, profile) }))
    .sort((a, b) => b.m.score - a.m.score);

  return (
    <div className="screen">
      <Ticks />
      <div className="gridlines" />

      <header className="topbar">
        <button className="back" onClick={() => go("jobs")}>
          ← 返回结果列表
        </button>
      </header>

      <div className="page-head">
        <h1 className="page-title">岗位对比</h1>
        <p className="page-sub">
          {picked.length ? `并排比较 ${picked.length} 个岗位，最多 4 个。` : "还没有选岗位。"}
        </p>
      </div>

      {picked.length === 0 ? (
        <div className="cmp-empty">
          <p>去岗位详情里点「加入对比」，选满 2 个就能在这里并排看。</p>
          <button className="btn primary" onClick={() => go("jobs")}>
            去看岗位
          </button>
        </div>
      ) : (
        <div className="cmp" style={{ gridTemplateColumns: `120px repeat(${picked.length}, 1fr)` }}>
          <div className="cmp-row-label" />
          {picked.map(({ job }, i) => (
            <div className="cmp-head" key={job.id}>
              {i === 0 && <span className="rec">推荐</span>}
              <h4>{job.company}</h4>
              <span className="cmp-title">{job.title}</span>
              <button
                className="btn sm"
                onClick={() => {
                  toggleCompare(job.id);
                }}
              >
                移除
              </button>
            </div>
          ))}

          <div className="cmp-row-label">匹配分</div>
          {picked.map(({ job, m }) => (
            <div className="cmp-cell strong" key={job.id + "-s"}>
              {m.score}
            </div>
          ))}

          <div className="cmp-row-label">薪资</div>
          {picked.map(({ job }) => (
            <div className="cmp-cell" key={job.id + "-p"}>
              {job.salary}
            </div>
          ))}

          <div className="cmp-row-label">城市</div>
          {picked.map(({ job }) => (
            <div className="cmp-cell" key={job.id + "-c"}>
              {job.city}
            </div>
          ))}

          <div className="cmp-row-label">类型</div>
          {picked.map(({ job }) => (
            <div className="cmp-cell" key={job.id + "-t"}>
              {job.employment}
            </div>
          ))}

          <div className="cmp-row-label">核验</div>
          {picked.map(({ job }) => (
            <div className="cmp-cell" key={job.id + "-v"}>
              <i className={`dot ${job.verify}`} />
              {job.verify === "ok" ? "已核验" : job.verify === "dead" ? "来源失效" : "待核验"}
            </div>
          ))}

          <div className="cmp-row-label">缺口</div>
          {picked.map(({ job, m }) => (
            <div className="cmp-cell" key={job.id + "-g"}>
              {m.gap.length + m.fail.length === 0 ? "无" : `${m.gap.length + m.fail.length} 项`}
            </div>
          ))}

          <div className="cmp-row-label">下一步</div>
          {picked.map(({ job }) => (
            <div className="cmp-cell" key={job.id + "-a"}>
              <button className="btn sm" onClick={() => go("interview")}>
                面这个
              </button>
            </div>
          ))}
        </div>
      )}

      {picked.length >= 2 && (
        <p className="cmp-note">
          推荐顺序：{picked.map((p) => p.job.company).join(" > ")}。
          {picked[0].job.company} 的匹配最高且硬性条件全部满足；
          后面的岗位各有缺口，需要先补证据。
        </p>
      )}

      <FlowRail
        steps={[
          { label: "设定条件", state: "done" },
          { label: "搜索结果", state: "done" },
          { label: "匹配详情", state: "done" },
          { label: "岗位对比", state: "now", sub: `${picked.length} / 4 个` },
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
