import Ticks from "../components/Ticks";
import FlowRail from "../components/FlowRail";
import { useProfile } from "../store";
import type { Route } from "../App";

type Props = {
  go: (r: Route) => void;
};

export default function ResumeDraft({ go }: Props) {
  const { profile } = useProfile();

  const pending = [
    ...profile.projects
      .filter((p) => !profile.answers[`proj-${p.id}`])
      .map((p) => ({ key: `proj-${p.id}`, label: `「${p.name}」里你的分工还没确认` })),
    // 只有真的上传过简历，才谈得上「实习时间待确认」
    ...(profile.resume && !profile.answers["resume-period"]
      ? [{ key: "resume-period", label: "实习起止时间还没确认" }]
      : []),
    ...(profile.stories.trim()
      ? []
      : [{ key: "stories", label: "主观经历是空的，这一栏只留了小标题" }]),
  ];

  const done = Object.keys(profile.answers).length;

  // 答案里存的是 questionId，展示时转成人能看懂的标签
  const LABELS: Record<string, string> = { stories: "经历", "resume-period": "简历" };
  const labelOf = (id: string) => {
    if (LABELS[id]) return LABELS[id];
    if (id.startsWith("proj-")) {
      const pid = id.slice(5);
      return profile.projects.find((p) => p.id === pid)?.name ?? "项目";
    }
    return "档案";
  };

  return (
    <div className="screen">
      <Ticks />
      <div className="gridlines" />

      <header className="topbar">
        <button className="back" onClick={() => go("resume-qa")}>
          ← 返回问答
        </button>
      </header>

      <div className="page-head">
        <h1 className="page-title">简历草稿</h1>
        <p className="page-sub">用确认过的事实写；没确认的地方标成「待确认」，不会替你编。</p>
      </div>

      <div className="draft-body">
        <article className="sheet">
          <div className="sheet-head">
            <h2>李思远</h2>
            <span>{profile.target.role ?? "前端开发"} · 2027 届 · 本科</span>
          </div>

          <section>
            <h5>教育背景</h5>
            <div className="sheet-row">
              <b>某某大学</b>
              <span>计算机科学与技术 · 2023.09 – 2027.06</span>
            </div>
          </section>

          <section>
            <h5>项目经历</h5>
            {profile.projects.length ? (
              profile.projects.map((p) => {
                const ok = !!profile.answers[`proj-${p.id}`];
                return (
                  <div className="sheet-item" key={p.id}>
                    <div className="si-head">
                      <b>{p.name}</b>
                      {!ok && <span className="tag-pending">分工待确认</span>}
                    </div>
                    <p>
                      负责{p.source === "github" ? "仓库" : "压缩包"}中的前端实现，
                      {ok ? "独立完成页面结构与交互。" : "具体范围待你确认后再写。"}
                    </p>
                  </div>
                );
              })
            ) : (
              <div className="sheet-empty">还没有项目。先去上传页加一个。</div>
            )}
          </section>

          <section>
            <h5>个人陈述</h5>
            {profile.stories.trim() ? (
              <p className="sheet-text">{profile.stories}</p>
            ) : (
              <div className="sheet-empty">这一段还是空的，简历里会留白。</div>
            )}
          </section>
        </article>

        <aside className="draft-side">
          <div className="cap">待确认 · {pending.length}</div>
          {pending.length ? (
            pending.map((p) => (
              <div className="pending" key={p.key}>
                <span>{p.label}</span>
                <button className="btn sm" onClick={() => go("resume-qa")}>
                  去确认
                </button>
              </div>
            ))
          ) : (
            <div className="pending">
              <span>都确认完了。</span>
            </div>
          )}

          <div className="cap" style={{ marginTop: 26 }}>
            本轮已确认 · {done}
          </div>
          <ul className="ans-list">
            {Object.entries(profile.answers).map(([k, v]) => (
              <li key={k}>
                <b>{labelOf(k)}</b>
                <span>{v}</span>
              </li>
            ))}
            {done === 0 && <li className="muted">还没有确认任何一条。</li>}
          </ul>
        </aside>
      </div>

      <footer className="save-bar">
        <span>草稿 · 未导出</span>
        <div style={{ display: "flex", gap: 10 }}>
          <button className="btn" disabled title="MVP 暂不导出">
            导出 PDF
          </button>
          <button className="btn" disabled title="MVP 暂不导出">
            导出 Word
          </button>
          <button className="btn primary" onClick={() => go("resume-qa")}>
            再改一版
          </button>
        </div>
      </footer>

      <FlowRail
        steps={[
          { label: "选择方式", state: "done" },
          { label: "读取档案", state: "done" },
          { label: "确认信息", state: "done" },
          { label: "生成草稿", state: "now", sub: `${pending.length} 处待确认` },
          { label: "检查与导出", state: "next" },
        ]}
      >
        <div className="sum">
          <div>
            <b>{pending.length}</b>
            <span>待确认</span>
          </div>
          <div>
            <b>{done}</b>
            <span>已确认</span>
          </div>
        </div>
      </FlowRail>
    </div>
  );
}
