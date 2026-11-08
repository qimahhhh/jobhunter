import { useEffect, useRef, useState } from "react";
import Top from "../components/Top";
import Band from "../components/Band";
import { useProfile } from "../store";
import { buildQuestions } from "../questions";
import { ApiError, confirmProfile, draftResume, type ResumeDraft as Draft } from "../api";
import type { Route } from "../App";

type Props = {
  go: (r: Route) => void;
};

export default function ResumeDraft({ go }: Props) {
  const { profile, patch, user } = useProfile();
  const [draft, setDraft] = useState<Draft | null>(null);
  const [status, setStatus] = useState<"idle" | "loading" | "ok" | "error">("idle");
  const [error, setError] = useState<string | null>(null);
  const started = useRef(false);

  async function generate() {
    setStatus("loading");
    setError(null);
    try {
      if (!profile.backendUserId) {
        throw new Error("还没有后端用户。请先在「上传资料」里上传一份简历。");
      }
      const profileId = profile.backendProfileId ?? (await confirmProfile(profile)).id;
      if (profileId !== profile.backendProfileId) patch({ backendProfileId: profileId });

      const result = await draftResume(profileId);
      setDraft(result);
      setStatus("ok");
      patch({
        draftResumeId: result.resumeId ?? undefined,
        draftVersion: result.version,
      });
    } catch (err) {
      const message =
        err instanceof ApiError && err.status === 503
          ? "后端没有配置模型 Key（503）。在 jobhunter/.env 填 DEEPSEEK_API_KEY 后重启后端。"
          : err instanceof ApiError && err.status === 404
            ? "后端找不到用户或画像，可能数据库被重置；请重新上传一次简历。"
            : (err as Error).message;
      setError(message);
      setStatus("error");
    }
  }

  // 进页面自动生成一次；没有后端用户时停在待生成状态，避免无意义报错
  useEffect(() => {
    if (started.current || !profile.backendUserId) return;
    started.current = true;
    void generate();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const pending = [
    ...profile.projects
      .filter((p) => !profile.answers[`proj-${p.id}`])
      .map((p) => ({ key: `proj-${p.id}`, label: `「${p.name}」里你的分工还没确认` })),
    ...(profile.missingInformation ?? []).flatMap((item, i) => {
      const key = `missing-${i}`;
      return profile.answers[key] ? [] : [{ key, label: `${item} 还没补充` }];
    }),
    // 只有真的上传过简历，才谈得上「实习时间待确认」
    ...(profile.resume && !profile.answers["resume-period"]
      ? [{ key: "resume-period", label: "实习起止时间还没确认" }]
      : []),
    ...(profile.stories.trim()
      ? []
      : [{ key: "stories", label: "主观经历是空的，这一栏只留了小标题" }]),
  ];

  // 只统计当前题目对应的答案，避免旧简历的答案混进来
  const questionIds = new Set(buildQuestions(profile).map((q) => q.id));
  const doneEntries = Object.entries(profile.answers).filter(([id]) => questionIds.has(id));
  const done = doneEntries.length;

  // 答案里存的是 questionId，展示时转成人能看懂的标签
  const LABELS: Record<string, string> = {
    stories: "经历",
    "resume-period": "简历",
    extra: "补充",
  };
  const labelOf = (id: string) => {
    if (LABELS[id]) return LABELS[id];
    if (id.startsWith("proj-")) {
      const pid = id.slice(5);
      return profile.projects.find((p) => p.id === pid)?.name ?? "项目";
    }
    return "档案";
  };

  return (
    <div className="shell" id="main">
      <Top
        onHome={() => go("home")}
        back={{ label: "返回简历", onClick: () => go("resume") }}
      />

      <main className="page">
        <div className="eyebrow">A 区 · 简历草稿</div>
        <h1 className="h1 mt-16">简历草稿</h1>
        <p className="lead">用确认过的事实写；没确认的地方标成「待确认」，不会替你编。</p>

        <div className="row between wrap mt-8" style={{ gap: 12, alignItems: "center" }}>
          <span className="small" style={status === "error" ? { color: "#b42318" } : undefined}>
            {status === "loading"
              ? "正在调用后端生成，通常 10–30 秒…"
              : status === "ok"
                ? `已生成 · 版本 ${draft?.version ?? 0}`
                : status === "error"
                  ? "生成失败"
                  : "尚未生成"}
          </span>
          <button
            className="pill solid"
            disabled={status === "loading"}
            onClick={() => void generate()}
            type="button"
          >
            {status === "ok" ? "重新生成" : "用模型生成"}
          </button>
        </div>
        {error && (
          <p className="small mt-8" style={{ color: "#b42318" }}>
            {error}
          </p>
        )}

        <div className="row between wrap mt-32" style={{ gap: 40, alignItems: "flex-start" }}>
          {draft ? (
            <article
              className="panel"
              style={{
                flex: "1 1 560px",
                maxWidth: 720,
                minWidth: 0,
                minHeight: 560,
                borderLeft: "8px solid var(--yellow)",
                padding: "clamp(24px, 4vw, 36px) clamp(18px, 3.5vw, 32px)",
              }}
            >
              <div
                className="row between wrap"
                style={{
                  gap: 12,
                  alignItems: "baseline",
                  borderBottom: "1px solid var(--line)",
                  paddingBottom: 18,
                }}
              >
                <h2 className="h2">{user?.name ?? "候选人"}</h2>
                <span className="small">
                  {draft.headline || profile.target.role || "求职方向待确认"}
                  {draft.version ? ` · v${draft.version}` : ""}
                </span>
              </div>

              {draft.summary && (
                <section className="mt-24">
                  <h3 className="eyebrow">概述</h3>
                  <p className="mt-8" style={{ whiteSpace: "pre-wrap" }}>
                    {draft.summary}
                  </p>
                </section>
              )}

              {draft.education.length > 0 && (
                <section className="mt-32">
                  <h3 className="eyebrow">教育背景</h3>
                  <ul className="mt-8">
                    {draft.education.map((item, i) => (
                      <li key={i}>{item}</li>
                    ))}
                  </ul>
                </section>
              )}

              {draft.experiences.length > 0 && (
                <section className="mt-32">
                  <h3 className="eyebrow">经历</h3>
                  {draft.experiences.map((exp, i) => (
                    <div
                      key={i}
                      style={{
                        borderTop: "1px solid var(--line)",
                        paddingTop: 12,
                        marginTop: 12,
                      }}
                    >
                      <b>{exp.heading}</b>
                      <ul className="mt-8">
                        {exp.bullets.map((bullet, j) => (
                          <li key={j}>
                            {bullet.text}
                            {bullet.sources.length > 0 && (
                              <span className="tag mute" style={{ marginLeft: 8 }}>
                                {bullet.sources.length} 条原文引用
                              </span>
                            )}
                          </li>
                        ))}
                      </ul>
                    </div>
                  ))}
                </section>
              )}

              {draft.skills.length > 0 && (
                <section className="mt-32">
                  <h3 className="eyebrow">技能</h3>
                  <div className="tags">
                    {draft.skills.map((skill) => (
                      <span className="tag" key={skill}>
                        {skill}
                      </span>
                    ))}
                  </div>
                </section>
              )}

              {draft.suggestions.length > 0 && (
                <section className="mt-32">
                  <h3 className="eyebrow">改写建议</h3>
                  <ul className="mt-8">
                    {draft.suggestions.slice(0, 4).map((item, i) => (
                      <li key={i}>{item}</li>
                    ))}
                  </ul>
                </section>
              )}

              {draft.degraded && (
                <p className="small mt-24" style={{ color: "#b42318" }}>
                  生成结果未通过原文校验，仅供演示参考。
                </p>
              )}
            </article>
          ) : (
            <article
              className="panel"
              style={{
                flex: "1 1 560px",
                maxWidth: 720,
                minWidth: 0,
                minHeight: 560,
                borderLeft: "8px solid var(--yellow)",
                padding: "clamp(24px, 4vw, 36px) clamp(18px, 3.5vw, 32px)",
              }}
            >
            <div
              className="row between wrap"
              style={{
                gap: 12,
                alignItems: "baseline",
                borderBottom: "1px solid var(--line)",
                paddingBottom: 18,
              }}
            >
              <h2 className="h2">{user?.name ?? "rael"}</h2>
              <span className="small">
                {profile.target.role ?? "前端开发"} · 2027 届 · 本科
              </span>
            </div>

            <section className="mt-24">
              <h3 className="eyebrow">教育背景</h3>
              <div
                className="row between wrap"
                style={{
                  gap: 12,
                  alignItems: "baseline",
                  borderTop: "1px solid var(--line)",
                  paddingTop: 10,
                  marginTop: 10,
                }}
              >
                <b>某某大学</b>
                <span className="small">计算机科学与技术 · 2023.09 – 2027.06</span>
              </div>
            </section>

            <section className="mt-32">
              <h3 className="eyebrow">项目经历</h3>
              {profile.projects.length ? (
                profile.projects.map((p) => {
                  const ok = !!profile.answers[`proj-${p.id}`];
                  return (
                    <div
                      key={p.id}
                      style={{
                        borderTop: "1px solid var(--line)",
                        paddingTop: 12,
                        marginTop: 12,
                      }}
                    >
                      <div className="row wrap" style={{ gap: 8, alignItems: "center" }}>
                        <b>{p.name}</b>
                        {!ok && <span className="tag mute">分工待确认</span>}
                      </div>
                      <p className="mt-8">
                        负责{p.source === "github" ? "仓库" : "压缩包"}中的前端实现，
                        {ok ? "独立完成页面结构与交互。" : "具体范围待你确认后再写。"}
                      </p>
                    </div>
                  );
                })
              ) : (
                <p className="small mt-16">还没有项目。先去上传页加一个。</p>
              )}
            </section>

            <section className="mt-32">
              <h3 className="eyebrow">个人陈述</h3>
              {profile.stories.trim() ? (
                <p className="mt-8" style={{ whiteSpace: "pre-wrap" }}>
                  {profile.stories}
                </p>
              ) : (
                <p className="small mt-8">这一段还是空的，简历里会留白。</p>
              )}
            </section>
          </article>
          )}

          <aside style={{ flex: "0 1 300px", minWidth: 260 }}>
            <div className="row between" style={{ gap: 12 }}>
              <span className="eyebrow">待确认 · {pending.length}</span>
            </div>
            <div className="col-list mt-8">
              <ul>
                {pending.length ? (
                  pending.map((p) => (
                    <li key={p.key} style={{ alignItems: "center" }}>
                      <span style={{ flex: 1, minWidth: 0 }}>{p.label}</span>
                      <button
                        className="pill sm"
                        onClick={() => go("resume")}
                        type="button"
                      >
                        去确认
                      </button>
                    </li>
                  ))
                ) : (
                  <li>
                    <span>都确认完了。</span>
                  </li>
                )}
              </ul>
            </div>

            <div className="eyebrow mt-32">本轮已确认 · {done}</div>
            <div className="col-list mt-8">
              <ul>
                {doneEntries.map(([k, v]) => (
                  <li key={k}>
                    <em>{labelOf(k)}</em>
                    <span>{v}</span>
                  </li>
                ))}
                {done === 0 && <li className="muted">还没有确认任何一条。</li>}
              </ul>
            </div>
          </aside>
        </div>

        <div
          className="row between wrap mt-48"
          style={{ gap: 16, borderTop: "1.5px solid var(--ink)", paddingTop: 18 }}
        >
          <span className="small">草稿 · 未导出</span>
          <div className="row wrap" style={{ gap: 10 }}>
            <button className="pill" disabled title="MVP 暂不导出" type="button">
              导出 PDF
            </button>
            <button className="pill" disabled title="MVP 暂不导出" type="button">
              导出 Word
            </button>
            <button className="pill solid" onClick={() => go("resume")} type="button">
              再改一版
            </button>
          </div>
        </div>
      </main>

      <Band
        step={1}
        total={4}
        label={`简历 · 第 2 步 · 草稿 · ${pending.length} 处待确认`}
        action={{ label: "完成，返回主页", onClick: () => go("home") }}
      />
    </div>
  );
}
