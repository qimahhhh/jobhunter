import { useRef, useState } from "react";
import Ticks from "../components/Ticks";
import { useProfile } from "../store";
import { checklist } from "../types";
import type { Route } from "../App";

export default function Upload({ go }: { go: (r: Route) => void }) {
  const { profile, patch } = useProfile();
  const [urlOpen, setUrlOpen] = useState(false);
  const [url, setUrl] = useState("");

  const resumeInput = useRef<HTMLInputElement>(null);
  const zipInput = useRef<HTMLInputElement>(null);

  const items = checklist(profile);
  const done = items.filter((i) => i.done).length;

  function pickResume(file?: File) {
    if (!file) return;
    patch({
      resume: { name: file.name, size: file.size, pages: 2, experiences: 0 },
    });
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
                {profile.resume ? "已上传" : "待上传"}
              </span>
            </div>

            {profile.resume ? (
              <div className="file-row">
                <div className="fico">PDF</div>
                <div className="fmeta">
                  <b>{profile.resume.name}</b>
                  <span>
                    {(profile.resume.size / 1024 / 1024).toFixed(1)} MB · {profile.resume.pages} 页
                  </span>
                </div>
                <div className="fops">
                  <button className="btn" onClick={() => resumeInput.current?.click()}>
                    替换
                  </button>
                  <button className="btn" onClick={() => patch({ resume: null })}>
                    移除
                  </button>
                </div>
              </div>
            ) : (
              <button className="drop" onClick={() => resumeInput.current?.click()}>
                <b>把简历拖到这里</b>
                <span>或点击选择文件 · PDF / Word / 图片 · ≤ 20 MB</span>
              </button>
            )}

            <input
              ref={resumeInput}
              type="file"
              accept=".pdf,.doc,.docx,.png,.jpg,.jpeg"
              hidden
              onChange={(e) => pickResume(e.target.files?.[0])}
            />
          </section>

          {/* 02 项目 */}
          <section className="up-sec">
            <div className="sec-head">
              <span className="idx">02</span>
              <h3>项目经历</h3>
              <span className="chip">
                {profile.projects.length} / 6
              </span>
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
