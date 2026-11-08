import { useRef, useState } from "react";
import Top from "../components/Top";
import Band from "../components/Band";
import { useProfile } from "../store";
import { checklist } from "../types";
import { ApiError, createUser, extractResume, type ExtractionResult } from "../api";
import type { Route } from "../App";

type Status = { kind: "info" | "ok" | "err"; text: string };

export default function Upload({ go }: { go: (r: Route) => void }) {
  const { profile, patch, user } = useProfile();
  const [urlOpen, setUrlOpen] = useState(false);
  const [url, setUrl] = useState("");
  const [busy, setBusy] = useState(false);
  const [status, setStatus] = useState<Status | null>(null);

  const resumeInput = useRef<HTMLInputElement>(null);
  const zipInput = useRef<HTMLInputElement>(null);

  const items = checklist(profile);
  const done = items.filter((i) => i.done).length;

  async function pickResume(file?: File) {
    if (!file) return;
    const ext = file.name.toLowerCase().split(".").pop();
    if (ext !== "pdf" && ext !== "docx") {
      setStatus({ kind: "err", text: "后端目前只解析 PDF / DOCX，图片请先转成 PDF 再上传。" });
      return;
    }

    setBusy(true);
    setStatus({ kind: "info", text: "正在解析简历并抽取档案……" });
    try {
      // 抽取带 user_id 后，后端会把原文 chunks 存成一条简历记录，后续确认/草稿要用
      let userId = profile.backendUserId;
      if (!userId) {
        const created = await createUser(user?.name ?? "求职者");
        userId = created.id;
        patch({ backendUserId: userId });
      }

      let result: ExtractionResult;
      try {
        result = await extractResume(file, userId);
      } catch (err) {
        // 本地存了 userId 但后端数据库被重置时，重新建一个用户再试一次
        if (err instanceof ApiError && err.status === 404) {
          const created = await createUser(user?.name ?? "求职者");
          userId = created.id;
          patch({ backendUserId: userId });
          result = await extractResume(file, userId);
        } else {
          throw err;
        }
      }

      const draft = result.profile;
      const skills = draft?.skills ?? [];
      const experiences = draft?.experiences ?? [];
      const story = [draft?.summary, ...experiences].filter(Boolean).join("\n");

      patch({
        resume: { name: file.name, size: file.size, pages: 2, experiences: experiences.length },
        summary: draft?.summary,
        skills,
        experiences,
        evidence: result.evidence,
        extraction: { degraded: result.degraded, notes: result.notes },
        recommendedRoles: result.recommended_roles,
        missingInformation: result.missing_information,
        resumeId: result.resume_id,
        backendUserId: userId,
        // 换了简历，旧的确认画像和草稿都失效
        backendProfileId: undefined,
        draftResumeId: undefined,
        draftVersion: undefined,
        stories: profile.stories.trim() ? profile.stories : story,
        // 换了简历，旧问答答案不再对应当前题目，清掉避免“只答一题却显示答完”
        answers: {},
      });

      setStatus({
        kind: result.degraded ? "info" : "ok",
        text: result.degraded
          ? "解析完成，但模型未配置，当前是规则降级结果。"
          : `解析完成：${skills.length} 项技能、${experiences.length} 段经历、${result.evidence.length} 条证据。`,
      });
    } catch (err) {
      const message =
        err instanceof ApiError && err.status === 503
          ? "后端没有配置模型 Key（503）。在 jobhunter/.env 填 DEEPSEEK_API_KEY 后重启后端即可；文件信息已记录。"
          : `解析失败：${(err as Error).message}。文件信息已记录，可继续手动填写。`;
      setStatus({ kind: "err", text: message });
      patch({
        resume: { name: file.name, size: file.size, pages: 2, experiences: 0 },
        summary: undefined,
        skills: [],
        evidence: [],
        extraction: undefined,
        recommendedRoles: [],
        missingInformation: [],
        resumeId: null,
        backendProfileId: undefined,
        draftResumeId: undefined,
        draftVersion: undefined,
        answers: {},
      });
    } finally {
      setBusy(false);
    }
  }

  function clearResume() {
    patch({
      resume: null,
      summary: undefined,
      skills: [],
      experiences: [],
      evidence: [],
      extraction: undefined,
      recommendedRoles: [],
      missingInformation: [],
      resumeId: null,
      backendProfileId: undefined,
      draftResumeId: undefined,
      draftVersion: undefined,
      answers: {},
    });
    setStatus(null);
  }

  function addProject(name: string, source: "github" | "zip") {
    patch({
      projects: [
        ...profile.projects,
        {
          id: `${source}-${Date.now()}`,
          name,
          source,
          fileCount: 0,
          isMain: profile.projects.length === 0,
        },
      ],
    });
  }

  function submitUrl() {
    const v = url.trim();
    if (!v) return;
    const m = v.match(/github\.com[/:]([^/]+)\/([^/#?]+)/i);
    addProject(m ? `${m[1]}/${m[2].replace(/\.git$/, "")}` : v, "github");
    setUrl("");
    setUrlOpen(false);
  }

  return (
    <div className="shell" id="main">
      <Top
        onHome={() => go("home")}
        back={{ label: "返回主页", onClick: () => go("home") }}
      />

      <main className="page">
        <div className="eyebrow">A 区 · 求职档案</div>
        <h1 className="h1 mt-16">建立求职档案</h1>
        <p className="lead">三块内容随时可改，离开自动保存。</p>

        <div className="row wrap mt-32" style={{ gap: 40, alignItems: "flex-start" }}>
          <div style={{ flex: "1 1 480px", minWidth: 360 }}>
            {/* 01 简历 */}
            <section>
              <div className="row between wrap" style={{ gap: 12, alignItems: "baseline" }}>
                <div className="row" style={{ gap: 12, alignItems: "baseline" }}>
                  <span className="eyebrow">01</span>
                  <h2 className="h2">个人简历</h2>
                </div>
                <span className={profile.resume && !busy ? "tag" : "tag mute"}>
                  {busy ? "解析中" : profile.resume ? "已上传" : "待上传"}
                </span>
              </div>

              {profile.resume ? (
                <div className="panel mt-16">
                  <div className="row between wrap" style={{ gap: 16 }}>
                    <div className="row" style={{ gap: 14, alignItems: "flex-start" }}>
                      <span className="tag nowrap">PDF</span>
                      <div>
                        <div className="h3">{profile.resume.name}</div>
                        <div className="small mt-8">
                          {(profile.resume.size / 1024 / 1024).toFixed(1)} MB ·{" "}
                          {profile.resume.pages} 页
                          {profile.resume.experiences > 0
                            ? ` · 识别 ${profile.resume.experiences} 段经历`
                            : ""}
                        </div>
                      </div>
                    </div>
                    <div className="row" style={{ gap: 8 }}>
                      <button
                        className="pill sm"
                        disabled={busy}
                        onClick={() => resumeInput.current?.click()}
                        type="button"
                      >
                        替换
                      </button>
                      <button className="pill sm" onClick={clearResume} type="button">
                        移除
                      </button>
                    </div>
                  </div>
                </div>
              ) : (
                <button
                  className="panel mt-16"
                  style={{
                    width: "100%",
                    textAlign: "left",
                    borderRadius: 0,
                    outlineColor: "var(--ink)",
                    outlineOffset: 3,
                  }}
                  disabled={busy}
                  onClick={() => resumeInput.current?.click()}
                  type="button"
                >
                  <span className="q" aria-hidden="true" style={{ display: "block" }}>
                    ＋
                  </span>
                  <span className="h2 mt-16" style={{ display: "block" }}>
                    {busy ? "正在解析……" : "把简历拖到这里"}
                  </span>
                  <span className="small mt-8" style={{ display: "block" }}>
                    或点击选择文件 · PDF / Word · ≤ 20 MB
                  </span>
                </button>
              )}

              <input
                ref={resumeInput}
                type="file"
                accept=".pdf,.docx"
                hidden
                onChange={(e) => {
                  const file = e.target.files?.[0];
                  e.target.value = "";
                  void pickResume(file);
                }}
              />

              {status && (
                <p className={status.kind === "err" ? "small warn mt-8" : "small mt-8"}>
                  {status.text}
                </p>
              )}

              {profile.skills && profile.skills.length > 0 && (
                <div className="row wrap mt-16" style={{ gap: 8 }}>
                  {profile.skills.map((skill) => (
                    <span className="tag" key={skill}>
                      {skill}
                    </span>
                  ))}
                </div>
              )}

              {profile.evidence && profile.evidence.length > 0 && (
                <p className="small mt-16">
                  已保留 {profile.evidence.length} 条简历证据引用，问答页会用到。
                </p>
              )}
            </section>

            {/* 02 项目 */}
            <section className="mt-48">
              <div className="row between wrap" style={{ gap: 12, alignItems: "baseline" }}>
                <div className="row" style={{ gap: 12, alignItems: "baseline" }}>
                  <span className="eyebrow">02</span>
                  <h2 className="h2">项目经历</h2>
                </div>
                <span className="tag">
                  <span className="num">{profile.projects.length}</span> / 6
                </span>
              </div>

              {profile.projects.length > 0 && (
                <div className="col-list mt-16">
                  <ul>
                    {profile.projects.map((p) => (
                      <li
                        key={p.id}
                        style={{ alignItems: "center", flexWrap: "wrap", padding: "14px 0" }}
                      >
                        <em className="mono">{p.source === "github" ? "GH" : "ZIP"}</em>
                        <span style={{ flex: 1, minWidth: 160 }}>
                          <b>{p.name}</b>
                          <span className="small" style={{ display: "block" }}>
                            {p.source === "github" ? "GitHub" : "压缩包"} · 已加入
                          </span>
                        </span>
                        <button
                          className={p.isMain ? "pill sm solid" : "pill sm"}
                          onClick={() =>
                            patch({
                              projects: profile.projects.map((x) => ({
                                ...x,
                                isMain: x.id === p.id,
                              })),
                            })
                          }
                          type="button"
                        >
                          {p.isMain ? "主项目" : "设为主项目"}
                        </button>
                        <button
                          className="pill sm"
                          onClick={() =>
                            patch({ projects: profile.projects.filter((x) => x.id !== p.id) })
                          }
                          type="button"
                        >
                          移除
                        </button>
                      </li>
                    ))}
                  </ul>
                </div>
              )}

              {urlOpen && (
                <div className="row mt-16" style={{ gap: 10, alignItems: "flex-end" }}>
                  <label className="field" style={{ flex: "1 1 260px", marginTop: 0 }}>
                    <span>GitHub 链接</span>
                    <input
                      autoFocus
                      value={url}
                      placeholder="https://github.com/owner/repo"
                      onChange={(e) => setUrl(e.target.value)}
                      onKeyDown={(e) => {
                        if (e.key === "Enter") submitUrl();
                        if (e.key === "Escape") setUrlOpen(false);
                      }}
                    />
                  </label>
                  <button className="pill solid" onClick={submitUrl} type="button">
                    拉取
                  </button>
                </div>
              )}

              <div className="row wrap mt-16" style={{ gap: 10 }}>
                <button className="pill" onClick={() => setUrlOpen(true)} type="button">
                  <span aria-hidden="true">+</span> 粘贴 GitHub 链接
                </button>
                <button
                  className="pill"
                  onClick={() => zipInput.current?.click()}
                  type="button"
                >
                  <span aria-hidden="true">+</span> 上传 ZIP 压缩包
                </button>
              </div>
              <input
                ref={zipInput}
                type="file"
                accept=".zip"
                hidden
                onChange={(e) => {
                  const f = e.target.files?.[0];
                  if (f) addProject(f.name.replace(/\.zip$/i, ""), "zip");
                }}
              />
            </section>

            {/* 03 主观经历 */}
            <section className="mt-48">
              <div className="row between wrap" style={{ gap: 12, alignItems: "baseline" }}>
                <div className="row" style={{ gap: 12, alignItems: "baseline" }}>
                  <span className="eyebrow">03</span>
                  <h2 className="h2">主观经历</h2>
                </div>
                <button className="pill sm" type="button">
                  上传文档
                </button>
              </div>
              <label className="field">
                <span>写清楚一件真实的事</span>
                <textarea
                  value={profile.stories}
                  maxLength={2000}
                  spellCheck={false}
                  placeholder="比如：在 XX 项目里我负责……最难的是……最后做到……"
                  onChange={(e) => patch({ stories: e.target.value })}
                />
              </label>
              <div className="row between mt-8">
                <span className="small">背景 → 你做了什么 → 结果</span>
                <span className="mono fs-13 muted">{profile.stories.length} / 2000</span>
              </div>
            </section>
          </div>

          {/* 右侧进度 */}
          <aside className="panel y yellow" style={{ flex: "0 1 320px", minWidth: 280 }}>
            <div className="eyebrow">档案完成度</div>
            <div className="row" style={{ gap: 10, alignItems: "baseline" }}>
              <span className="dest-no num">{done}</span>
              <span className="fs-13">/ 6 项</span>
            </div>
            <div className="col-list mt-16">
              <ul>
                {items.map((i, n) => (
                  <li
                    key={i.key}
                    style={{ alignItems: "center", justifyContent: "space-between" }}
                  >
                    <b className="num">{String(n + 1).padStart(2, "0")}</b>
                    <span style={{ flex: 1 }}>{i.label}</span>
                    {i.done ? (
                      <span className="tag">已填</span>
                    ) : (
                      <span className="tag dash">未填</span>
                    )}
                  </li>
                ))}
              </ul>
            </div>
            <p className="lead">
              至少完成「个人简历」，右侧的匹配档案才有内容可生成。
            </p>
            <button
              className="linkish mt-8"
              type="button"
              onClick={() => go("jobs")}
            >
              目标岗位 / 城市 / 类型 → 去岗位页设定
            </button>
          </aside>
        </div>

        <div
          className="row between wrap mt-48"
          style={{ gap: 16, borderTop: "1.5px solid var(--ink)", paddingTop: 18 }}
        >
          <span className="small">已自动保存</span>
          <button className="pill solid" onClick={() => go("home")} type="button">
            完成，返回主页
          </button>
        </div>
      </main>

      <Band step={1} total={4} label={`简历 · 第 1 步 · 档案 ${done}/6`} />
    </div>
  );
}
