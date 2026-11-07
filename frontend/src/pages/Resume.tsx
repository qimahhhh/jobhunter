import Ticks from "../components/Ticks";
import FlowRail from "../components/FlowRail";
import { useProfile } from "../store";
import type { Route } from "../App";

export default function Resume({ go }: { go: (r: Route) => void }) {
  const { profile } = useProfile();
  const hasResume = !!profile.resume;

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
        <h1 className="page-title">简历</h1>
        <p className="page-sub">先决定：写一份新的，还是改一份已有的。</p>
      </div>

      <div className="opt-wrap">
        <div className="opt">
          <div className="kicker">01 / Create</div>
          <h3>生成一份新简历</h3>
          <p>用你上传的档案和目标岗位从零写一份。系统先读完档案，再把里面说不清的地方一条条问你。</p>
          <div className="need">
            需要：个人档案 + 目标岗位
            <br />
            动态题量 · 预计 6–9 个问题
          </div>
          <button className="btn primary" onClick={() => go("resume-qa")}>
            开始生成
          </button>
        </div>

        <div className={hasResume ? "opt" : "opt dim"}>
          <div className="kicker">02 / Revise</div>
          <h3>修改已有简历</h3>
          <p>读你上传的那份，先诊断问题（空泛、缺证据、冗余），再只针对疑点提问，最后给你一版改好的。</p>
          <div className="need">
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
            <button className="btn primary" onClick={() => go("resume-qa")}>
              开始诊断
            </button>
          ) : (
            <button className="opt-link" onClick={() => go("upload")}>
              先去上传一份 →
            </button>
          )}
        </div>
      </div>

      <FlowRail
        steps={[
          { label: "选择方式", state: "now", sub: "现在在这里" },
          { label: "读取档案", state: "next" },
          { label: "确认信息", state: "next" },
          { label: "生成草稿", state: "next" },
          { label: "检查与导出", state: "next" },
        ]}
      />
      <footer className="meta">
        <span>AI Job Hunter / 2026</span>
        <span>简历 · 岗位 · 面试</span>
      </footer>
    </div>
  );
}
