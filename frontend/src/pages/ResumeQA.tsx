import { useState } from "react";
import Top from "../components/Top";
import Band from "../components/Band";
import { useProfile } from "../store";
import { buildQuestions } from "../questions";
import type { Route } from "../App";

export default function ResumeQA({ go }: { go: (r: Route) => void }) {
  const { profile, patch } = useProfile();
  const questions = buildQuestions(profile);

  const [index, setIndex] = useState(() => {
    // 回到本页时从第一道没答过的题开始，而不是永远从第 1 题重来
    const next = questions.findIndex((q) => !profile.answers[q.id]);
    return next === -1 ? questions.length : next;
  });
  const [free, setFree] = useState("");

  // 只统计当前题目对应的答案：换了简历后旧答案不应再计入
  const answeredItems = questions.filter((q) => profile.answers[q.id]);
  const answered = answeredItems.length;
  const finished = index >= questions.length;
  const q = questions[index];

  function answer(value: string) {
    if (!q) return;
    patch({ answers: { ...profile.answers, [q.id]: value } });
    setFree("");
    setIndex((i) => i + 1);
  }

  return (
    <div className="shell" id="main">
      <Top
        onHome={() => go("home")}
        back={{ label: "返回上一步", onClick: () => go("resume") }}
      />

      <main className="page">
        <div className="row between wrap" style={{ gap: 12, alignItems: "flex-start" }}>
          <div className="row wrap" style={{ gap: 12, alignItems: "baseline" }}>
            <span className="eyebrow">A 区 · 确认信息</span>
            {!finished && (
              <span className="tag mono">
                问题 {String(index + 1).padStart(2, "0")} /{" "}
                {String(questions.length).padStart(2, "0")}
              </span>
            )}
          </div>
          {!finished && (
            <button
              className="pill sm"
              onClick={() => setIndex((i) => i + 1)}
              type="button"
            >
              跳过
            </button>
          )}
        </div>

        <div
          className="row between wrap mt-24"
          style={{ gap: 48, alignItems: "flex-start" }}
        >
          <div style={{ flex: "1 1 520px", maxWidth: 760, minWidth: 0 }}>
            {finished ? (
              <>
                <h1 className="h1">档案里能问的都问完了。</h1>
                <p className="lead">问完了 {answered} 个问题，剩下的交给生成。</p>
                <p className="small mt-16">
                  <b>接下来</b>：用这些确认过的事实生成草稿；没答的地方会在简历里标成「待确认」，不会替你编。
                </p>
                <div className="row wrap mt-32" style={{ gap: 12 }}>
                  <button className="pill" onClick={() => go("resume")} type="button">
                    回到上一步
                  </button>
                  <button
                    className="pill solid"
                    onClick={() => go("resume-draft")}
                    type="button"
                  >
                    生成草稿
                  </button>
                </div>
              </>
            ) : (
              <>
                <p className="small">只问档案里说不清的地方，答完一条就少一个疑点。</p>
                <h1 className="h1 mt-16">{q.title}</h1>
                <p className="small mt-16">
                  <b>依据</b>：{q.basis}
                </p>

                <div className="stack mt-32" style={{ gap: 10 }}>
                  {q.options.map((o) => (
                    <button
                      className="pill"
                      key={o}
                      style={{
                        width: "100%",
                        justifyContent: "flex-start",
                        minHeight: 52,
                        paddingLeft: 20,
                      }}
                      onClick={() => answer(o)}
                      type="button"
                    >
                      {o}
                    </button>
                  ))}
                </div>

                <label className="field mt-16">
                  <span>自定义回答</span>
                  <input
                    value={free}
                    placeholder={q.placeholder}
                    onChange={(e) => setFree(e.target.value)}
                    onKeyDown={(e) => {
                      if (e.key === "Enter" && free.trim()) answer(free.trim());
                    }}
                  />
                </label>

                <div className="row between wrap mt-24" style={{ gap: 12 }}>
                  <button
                    className="linkish"
                    onClick={() => setIndex(questions.length)}
                    type="button"
                  >
                    就这些，用现有信息继续 →
                  </button>
                  <button
                    className="pill solid"
                    disabled={!free.trim()}
                    onClick={() => answer(free.trim())}
                    type="button"
                  >
                    确认并继续
                  </button>
                </div>
              </>
            )}
          </div>

          {answered > 0 && (
            <aside style={{ flex: "0 1 300px", minWidth: 260 }}>
              <div className="eyebrow">已确认 · {answered} 条</div>
              <div className="col-list mt-8">
                <ul>
                  {answeredItems.map((item) => (
                    <li key={item.id}>
                      <em>{item.tag}</em>
                      <span>{profile.answers[item.id]}</span>
                    </li>
                  ))}
                </ul>
              </div>
            </aside>
          )}
        </div>
      </main>

      <Band
        step={1}
        total={4}
        label={
          finished
            ? "简历 · 第 2 步 · 确认信息 · 已问完"
            : `简历 · 第 2 步 · 确认信息 ${Math.min(index + 1, questions.length)}/${questions.length} · 还剩 ${Math.max(
                questions.length - index - 1,
                0
              )}`
        }
      />
    </div>
  );
}
