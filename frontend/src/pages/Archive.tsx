import Top from "../components/Top";
import Band from "../components/Band";
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
    <div className="shell" id="main">
      <Top
        onHome={() => go("home")}
        back={{ label: "返回主页", onClick: () => go("home") }}
      />

      <main className="page">
        <div className="eyebrow">匹配档案</div>
        <h1 className="h1 mt-16">匹配档案</h1>
        <p className="lead">
          {done === 0
            ? "还没有内容。档案不是填出来的，是从简历、岗位、面试三块里长出来的。"
            : `已经完成 ${done} 项，${done === items.length ? "齐全了。" : "还差几块。"}`}
        </p>

        <div className="row mt-32" style={{ gap: 24, alignItems: "flex-end" }}>
          <div
            className="num"
            style={{ fontSize: "clamp(84px, 12vw, 168px)", lineHeight: 0.78 }}
          >
            {done}
          </div>
          <div className="stack" style={{ paddingBottom: 10 }}>
            <span className="num" style={{ fontSize: 30, lineHeight: 1 }}>
              / {items.length}
            </span>
            <span className="small">项 · 完成度 {pct}%</span>
          </div>
        </div>

        <div className="row mt-16" style={{ gap: 6 }} aria-hidden="true">
          {items.map((i) => (
            <i
              key={i.key}
              style={{
                width: "clamp(22px, 4vw, 44px)",
                height: 8,
                background: i.done ? "var(--ink)" : "var(--line)",
              }}
            />
          ))}
        </div>

        <div className="row wrap mt-16" style={{ gap: 6 }}>
          {items.map((i) => (
            <span key={i.key} className={i.done ? "tag" : "tag mute"}>
              {i.done ? "✓" : "·"} {i.label}
            </span>
          ))}
        </div>

        {done === 0 && (
          <div className="panel y mt-24">
            <p className="fs-13">
              至少完成「个人简历」，档案才有内容可生成。岗位和面试会让它更准。
            </p>
          </div>
        )}

        <div className="mt-32" style={{ borderTop: "1.5px solid var(--ink)" }}>
          <div
            style={{
              display: "grid",
              gridTemplateColumns: "minmax(56px, 72px) 1fr auto",
              alignItems: "center",
              gap: 12,
              padding: "18px 0",
              borderBottom: "1px solid var(--line)",
            }}
          >
            <span className="h3">简历</span>
            <span className="row" style={{ gap: 8 }}>
              <i className={profile.resume ? "dot" : "dot hollow"} />
              <span className={profile.resume ? "fs-13" : "small"}>{resumeStatus}</span>
            </span>
            <button className="pill sm" onClick={() => go("upload")} type="button">
              {profile.resume ? "查看" : "去上传"}
            </button>
          </div>

          <div
            style={{
              display: "grid",
              gridTemplateColumns: "minmax(56px, 72px) 1fr auto",
              alignItems: "center",
              gap: 12,
              padding: "18px 0",
              borderBottom: "1px solid var(--line)",
            }}
          >
            <span className="h3">岗位</span>
            <span className="row" style={{ gap: 8 }}>
              <i
                className={
                  profile.target.city || profile.target.role ? "dot" : "dot hollow"
                }
              />
              <span
                className={
                  profile.target.city || profile.target.role ? "fs-13" : "small"
                }
              >
                {jobsStatus}
              </span>
            </span>
            <button className="pill sm" onClick={() => go("jobs")} type="button">
              {profile.target.city || profile.target.role ? "查看" : "去搜索"}
            </button>
          </div>

          <div
            style={{
              display: "grid",
              gridTemplateColumns: "minmax(56px, 72px) 1fr auto",
              alignItems: "center",
              gap: 12,
              padding: "18px 0",
              borderBottom: "1px solid var(--line)",
            }}
          >
            <span className="h3">面试</span>
            <span className="row" style={{ gap: 8 }}>
              <i className="dot hollow" />
              <span className="small">{interviewStatus}</span>
            </span>
            <button
              className="pill sm"
              disabled={!profile.target.city && !profile.target.role}
              onClick={() => go("interview")}
              type="button"
            >
              {profile.target.city || profile.target.role
                ? "开始面试"
                : "需要先有目标岗位"}
            </button>
          </div>
        </div>

        <div className="eyebrow mt-32">技能标签 · {skills.length}</div>
        <div className="row wrap mt-8" style={{ gap: 6 }}>
          {shown.length ? (
            shown.map((s) => (
              <span className="tag" key={s}>
                {s}
              </span>
            ))
          ) : (
            <span className="tag mute">要等简历进来才有</span>
          )}
          {rest > 0 && <span className="tag mute">+ {rest}</span>}
        </div>

        <div className="eyebrow mt-32">缺口 · {gaps.length}</div>
        <div className="mt-8" style={{ borderTop: "1.5px solid var(--ink)" }}>
          {gaps.length ? (
            gaps.map((g) => (
              <div
                key={g.text}
                className="row between wrap"
                style={{
                  gap: 16,
                  padding: "14px 0",
                  borderBottom: "1px solid var(--line)",
                }}
              >
                <div className="row" style={{ gap: 10, alignItems: "baseline" }}>
                  <span className="tag">{g.kind}</span>
                  <span className="fs-13">{g.text}</span>
                </div>
                <button className="pill sm" onClick={() => go("upload")} type="button">
                  去补充
                </button>
              </div>
            ))
          ) : (
            <div
              className="row"
              style={{ gap: 10, padding: "14px 0", borderBottom: "1px solid var(--line)" }}
            >
              <span className="tag mute">·</span>
              <span className="small">
                {done === 0
                  ? "档案还是空的，先上传简历才谈得上缺口。"
                  : "暂时没有明显缺口，等岗位匹配出来再说。"}
              </span>
            </div>
          )}
        </div>

        <div className="row between wrap mt-48" style={{ gap: 16 }}>
          <span className="small">最后更新 · 刚刚</span>
          <button
            className="pill solid"
            onClick={() =>
              go(profile.target.city || profile.target.role ? "interview" : "upload")
            }
            type="button"
          >
            {profile.target.city || profile.target.role
              ? "开始一场模拟面试"
              : "先去上传资料"}
          </button>
        </div>
      </main>

      <Band step={1} total={4} label={`匹配档案 · 完成 ${done} / ${items.length}`} />
    </div>
  );
}
