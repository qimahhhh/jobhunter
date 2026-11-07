import Ticks from "../components/Ticks";
import FlowRail from "../components/FlowRail";
import { useProfile } from "../store";
import { checklist } from "../types";
import { sortedJobs } from "../jobs";
import type { Route } from "../App";

type Props = {
  go: (r: Route) => void;
};

export default function Archive({ go }: Props) {
  const { profile } = useProfile();
  const items = checklist(profile);
  const done = items.filter((i) => i.done).length;
  const pct = Math.round((done / items.length) * 100);

  const ranked = sortedJobs(profile);
  const main = ranked[0];
  const gaps =
    done === 0
      ? []
      : [
          ...main.match.gap.map((t) => ({
            kind: "缺证据",
            text: `「${t}」在档案里没有可量化的结果`,
          })),
          ...main.match.fail.map((t) => ({
            kind: "未覆盖",
            text: `目标岗位要求的「${t}」还没有经历`,
          })),
        ].slice(0, 3);

  /** mock：技能标签现在由项目名 + 简历存在与否拼出来，接后端后换成 skills[] */
  const skills = [
    ...(profile.resume ? ["React", "TypeScript", "Vite"] : []),
    ...profile.projects.map((p) => p.name),
    ...(profile.stories.trim() ? ["主观经历"] : []),
  ];
  const shown = skills.slice(0, 8);
  const rest = skills.length - shown.length;

  const resumeStatus = profile.resume
    ? `已上传 · ${profile.resume.pages} 页`
    : "还没有上传";
  const jobsStatus = profile.target.city || profile.target.role
    ? `已匹配 ${ranked.length} 个 · 最高 ${ranked[0].match.score} 分`
    : "还没有设定条件";
  const interviewStatus = "未开始";

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
        <h1 className="page-title">匹配档案</h1>
        <p className="page-sub">
          {done === 0
            ? "还没有内容。档案不是填出来的，是从简历、岗位、面试三块里长出来的。"
            : `已经完成 ${done} 项，${done === items.length ? "齐全了。" : "还差几块。"}`}
        </p>
      </div>

      <div className="arch">
        <div className="big">
          <b>{done}</b>
          <span>/ {items.length} 项</span>
          <em>完成度 {pct}%</em>
        </div>

        <div className="seg">
          {items.map((i) => (
            <i key={i.key} className={i.done ? "on" : ""} />
          ))}
        </div>

        {done === 0 && (
          <div className="note-bar">
            至少完成「个人简历」，档案才有内容可生成。岗位和面试会让它更准。
          </div>
        )}

        <div className="arow">
          <span className="nm">简历</span>
          <span className={profile.resume ? "st ok" : "st"}>{resumeStatus}</span>
          <div className="act">
            <button className="btn sm" onClick={() => go("upload")}>
              {profile.resume ? "查看" : "去上传"}
            </button>
          </div>
        </div>

        <div className="arow">
          <span className="nm">岗位</span>
          <span className={profile.target.city || profile.target.role ? "st ok" : "st"}>
            {jobsStatus}
          </span>
          <div className="act">
            <button className="btn sm" onClick={() => go("jobs")}>
              {profile.target.city || profile.target.role ? "查看" : "去搜索"}
            </button>
          </div>
        </div>

        <div className="arow">
          <span className="nm">面试</span>
          <span className="st">{interviewStatus}</span>
          <div className="act">
            <button
              className="btn sm"
              disabled={!profile.target.city && !profile.target.role}
              onClick={() => go("interview")}
            >
              {profile.target.city || profile.target.role ? "开始面试" : "需要先有目标岗位"}
            </button>
          </div>
        </div>

        <div className="sect">技能标签 · {skills.length}</div>
        <div className="tags">
          {shown.length ? (
            shown.map((s) => (
              <span className="tag" key={s}>
                {s}
              </span>
            ))
          ) : (
            <span className="tag dim">要等简历进来才有</span>
          )}
          {rest > 0 && <span className="tag dim">+ {rest}</span>}
        </div>

        <div className="sect">缺口 · {gaps.length}</div>
        {gaps.length ? (
          gaps.map((g) => (
            <div className="gap" key={g.text}>
              <em>{g.kind}</em>
              <span>{g.text}</span>
              <div className="act">
                <button className="btn sm" onClick={() => go("upload")}>
                  去补充
                </button>
              </div>
            </div>
          ))
        ) : (
          <div className="gap">
            <em>·</em>
            <span>
              {done === 0
                ? "档案还是空的，先上传简历才谈得上缺口。"
                : "暂时没有明显缺口，等岗位匹配出来再说。"}
            </span>
          </div>
        )}
      </div>

      <footer className="save-bar">
        <span>最后更新 · 刚刚</span>
        <button
          className="btn primary"
          onClick={() => go(profile.target.city || profile.target.role ? "interview" : "upload")}
        >
          {profile.target.city || profile.target.role ? "开始一场模拟面试" : "先去上传资料"}
        </button>
      </footer>

      <FlowRail
        steps={[
          { label: "读取档案", state: "done" },
          { label: "匹配岗位", state: profile.target.city || profile.target.role ? "done" : "next" },
          { label: "模拟面试", state: "next" },
          { label: "生成报告", state: "next" },
        ]}
      >
        <div className="sum">
          <div>
            <b>{done}</b>
            <span>完成项</span>
          </div>
          <div>
            <b>{pct}%</b>
            <span>完成度</span>
          </div>
        </div>
      </FlowRail>
    </div>
  );
}
