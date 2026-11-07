import { useRef, useState } from "react";
import Ticks from "../components/Ticks";
import { useProfile } from "../store";
import { checklist } from "../types";
import { ApiError, extractResume } from "../api";
import type { Route } from "../App";

type Status = { kind: "info" | "ok" | "err"; text: string };

export default function Upload({ go }: { go: (r: Route) => void }) {
  const { profile, patch } = useProfile();
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
      const result = await extractResume(file);
      const draft = result.profile;
      const skills = draft?.skills ?? [];
      const experiences = draft?.experiences ?? [];
      const story = [draft?.summary, ...experiences].filter(Boolean).join("\n");

      patch({
        resume: { name: file.name, size: file.size, pages: 2, experiences: experiences.length },
        summary: draft?.summary,
        skills,
        evidence: result.evidence,
        extraction: { degraded: result.degraded, notes: result.notes },
        stories: profile.stories.trim() ? profile.stories : story,
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
      evidence: [],
      extraction: undefined,
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
    <div className="screen">
      <Ticks />
      <div className="gridlines" />

      <header className="topbar">
        <button className="back" onClick={() => go("home")}>
          ← 返回主页
        </button>
      </header>

      <div className="page-head">
        <h1 className="page-title">建立求职档案</h1>
        <p className="page-sub">三块内容随时可改，离开自动保存。</p>
      </div>

      <div className="up-body">
        <div className="up-left">
          {/* 01 简历 */}
          <section className="up-sec">
            <div className="sec-head">
              <span className="idx">01</span>
              <h3>个人简历</h3>
              <span className={profile.resume ? "chip ok" : "chip"}>
                {busy ? "解析中" : profile.resume ? "已上传" : "待上传"}
              </span>
            </div>

            {profile.resume ? (
              <div className="file-row">
                <div className="fico">PDF</div>
                <div className="fmeta">
                  <b>{profile.resume.name}</b>
                  <span>
                    {(profile.resume.size / 1024 / 1024).toFixed(1)} MB · {profile.resume.pages} 页
                    {profile.resume.experiences > 0
                      ? ` · 识别 ${profile.resume.experiences} 段经历`
                      : ""}
                  </span>
                </div>
                <div className="fops">
                  <button className="btn" disabled={busy} onClick={() => resumeInput.current?.click()}>
                    替换
                  </button>
                  <button className="btn" onClick={clearResume}>
                    移除
                  </button>
                </div>
              </div>
            ) : (
              <button className="drop" disabled={busy} onClick={() => resumeInput.current?.click()}>
                <b>{busy ? "正在解析……" : "把简历拖到这里"}</b>
                <span>或点击选择文件 · PDF / Word · ≤ 20 MB</span>
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

            {status && <p className={`up-status ${status.kind}`}>{status.text}</p>}

            {profile.skills && profile.skills.length > 0 && (
              <div className="tags">
                {profile.skills.map((skill) => (
                  <span className="tag" key={skill}>
                    {skill}
                  </span>
                ))}
              </div>
            )}

            {profile.evidence && profile.evidence.length > 0 && (
              <p className="hint">已保留 {profile.evidence.length} 条简历证据引用，问答页会用到。</p>
            )}
          </section>

          {/* 02 项目 */}
          <section className="up-sec">
            <div className="sec-head">
              <span className="idx">02</span>
              <h3>项目经历</h3>
              <span className="chip">{profile.projects.length} / 6</span>
            </div>

            {profile.projects.map((p) => (
              <div className="proj-row" key={p.id}>
                <div className="pico">{p.source === "github" ? "GH" : "ZIP"}</div>
                <div className="pmeta">
                  <b>{p.name}</b>
                  <span>{p.source === "github" ? "GitHub" : "压缩包"} · 已加入</span>
                </div>
                <button
                  className={p.isMain ? "pin on" : "pin"}
                  onClick={() =>
                    patch({
                      projects: profile.projects.map((x) => ({ ...x, isMain: x.id === p.id })),
                    })
                  }
                >
                  {p.isMain ? "主项目" : "设为主项目"}
                </button>
                <button
                  className="btn"
                  onClick={() => patch({ projects: profile.projects.filter((x) => x.id !== p.id) })}
                >
                  移除
                </button>
              </div>
            ))}

            {urlOpen && (
              <div className="url-row">
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
                <button className="btn primary sm" onClick={submitUrl}>
                  拉取
                </button>
              </div>
            )}

            <div className="add-row">
              <button className="add-btn" onClick={() => setUrlOpen(true)}>
                <b>+</b>粘贴 GitHub 链接
              </button>
              <button className="add-btn" onClick={() => zipInput.current?.click()}>
                <b>+</b>上传 ZIP 压缩包
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
          <section className="up-sec">
            <div className="sec-head">
              <span className="idx">03</span>
              <h3>主观经历</h3>
              <button className="btn sm" style={{ marginLeft: "auto" }}>
                上传文档
              </button>
            </div>
            <textarea
              className="story"
              value={profile.stories}
              maxLength={2000}
              spellCheck={false}
              placeholder="比如：在 XX 项目里我负责……最难的是……最后做到……"
              onChange={(e) => patch({ stories: e.target.value })}
            />
            <div className="ta-foot">
              <span>背景 → 你做了什么 → 结果</span>
              <span>{profile.stories.length} / 2000</span>
            </div>
          </section>
        </div>

        {/* 右侧进度 */}
        <aside className="up-right">
          <div className="pct">
            <b>{done}</b>
            <span>/ 6</span>
          </div>
          <ul className="check-list">
            {items.map((i) => (
              <li key={i.key} className={i.done ? "on" : ""}>
                {i.label}
                {i.where === "jobs" && !i.done && (
                  <button className="mini" onClick={() => go("jobs")}>
                    去设定
                  </button>
                )}
              </li>
            ))}
          </ul>
          <p className="hint">至少完成「个人简历」，右侧的匹配档案才有内容可生成。</p>
        </aside>
      </div>

      <footer className="save-bar">
        <span>已自动保存</span>
        <button className="btn primary" onClick={() => go("home")}>
          完成，返回主页
        </button>
      </footer>
    </div>
  );
}
