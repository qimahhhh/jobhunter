import Top from "../components/Top";
import Band from "../components/Band";
import { useProfile } from "../store";
import type { Route } from "../App";

export default function Resume({ go }: { go: (r: Route) => void }) {
  const { profile } = useProfile();
  const hasResume = !!profile.resume;

  return (
    <div className="shell" id="main">
      <Top
        onHome={() => go("home")}
        back={{ label: "返回主页", onClick: () => go("home") }}
      />

      <main className="page">
        <div className="eyebrow">A 区 · 简历</div>
        <h1 className="h1 mt-16">简历</h1>
        <p className="lead">先决定：写一份新的，还是改一份已有的。</p>

        <div className="row wrap mt-32" style={{ gap: 16, alignItems: "flex-start" }}>
          <section className="panel" style={{ flex: "1 1 420px", minWidth: 0 }}>
            <div className="eyebrow">01 / Create</div>
            <h2 className="h2 mt-8">生成一份新简历</h2>
            <p className="lead">
              用你上传的档案和目标岗位从零写一份。系统先读完档案，再把里面说不清的地方一条条问你。
            </p>
            <div className="mt-16">
              <div className="small">需要：个人档案 + 目标岗位</div>
              <div className="small">
                动态题量 · 预计 <span className="num">6–9</span> 个问题
              </div>
            </div>
            <button
              className="pill solid mt-24"
              onClick={() => go("resume-draft")}
              type="button"
            >
              开始生成
            </button>
          </section>

          <section className="panel" style={{ flex: "1 1 420px", minWidth: 0 }}>
            <div className="row between wrap" style={{ gap: 8 }}>
              <span className="eyebrow">02 / Revise</span>
              <span className={hasResume ? "tag" : "tag mute"}>
                {hasResume ? "可修改" : "还没有简历"}
              </span>
            </div>
            <h2 className={hasResume ? "h2 mt-8" : "h2 mt-8 muted"}>修改已有简历</h2>
            <p className="lead">
              读你上传的那份，先诊断问题（空泛、缺证据、冗余），再只针对疑点提问，最后给你一版改好的。
            </p>
            <div className="small mt-16">
              {hasResume ? (
                <>
                  使用：{profile.resume?.name}
                  <br />
                  已解析 · 可直接开始
                </>
              ) : (
                <>
                  还没有可修改的简历
                  <br />
                  先去上传一份
                </>
              )}
            </div>
            {hasResume ? (
              <button
                className="pill solid mt-24"
                onClick={() => go("resume-draft")}
                type="button"
              >
                开始诊断
              </button>
            ) : (
              <button className="pill mt-24" onClick={() => go("upload")} type="button">
                先去上传一份 →
              </button>
            )}
          </section>
        </div>
      </main>

      <Band step={1} total={4} label="简历 · 第 1 步 · 选择方式" />
    </div>
  );
}
