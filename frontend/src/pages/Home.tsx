import { useState } from "react";
import Edge from "../components/Edge";
import Ticks from "../components/Ticks";
import UserBlock from "../components/UserBlock";
import LoginModal from "../components/LoginModal";
import Logo from "../components/Logo";
import Wordmark from "../components/Wordmark";
import { useProfile } from "../store";
import type { Route } from "../App";

function ResumeArt() {
  return (
    <svg width="120" height="98" viewBox="0 0 120 98" fill="none">
      {/* 纸：右上角折起 */}
      <path
        d="M36 7h38l15 15v66a3 3 0 0 1-3 3H36a3 3 0 0 1-3-3V10a3 3 0 0 1 3-3Z"
        stroke="#141414"
        strokeWidth="1.2"
        strokeLinejoin="round"
      />
      <path d="M74 7v12a3 3 0 0 0 3 3h12" stroke="#141414" strokeWidth="1.2" strokeLinejoin="round" />
      <path d="M44 34h34M44 44h34M44 54h22" stroke="#141414" strokeWidth="1.2" strokeOpacity=".32" />
      {/* 实心块给重心，不然整张图太飘 */}
      <rect x="44" y="64" width="30" height="4" fill="#141414" />
      {/* 通过 */}
      <circle cx="88" cy="74" r="10" fill="#fff" stroke="#141414" strokeWidth="1.2" />
      <path d="M83.6 74.2l3.2 3.4 6.2-7" stroke="#141414" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  );
}

function JobsArt() {
  return (
    <svg width="120" height="98" viewBox="0 0 120 98" fill="none">
      <rect x="14" y="12" width="64" height="16" rx="4" stroke="#141414" strokeWidth="1.2" />
      <path d="M24 20h20" stroke="#141414" strokeWidth="1.2" strokeOpacity=".32" />

      {/* 中间一行反白：表示"这一个已被选中" */}
      <rect x="14" y="36" width="64" height="16" rx="4" fill="#141414" />
      <path d="M24 44h26" stroke="#fff" strokeWidth="1.4" />
      <path d="M62 44h8" stroke="#fff" strokeWidth="1.4" strokeOpacity=".55" />

      <rect x="14" y="60" width="64" height="16" rx="4" stroke="#141414" strokeWidth="1.2" />
      <path d="M24 68h14" stroke="#141414" strokeWidth="1.2" strokeOpacity=".32" />

      {/* 定位针 */}
      <path
        d="M96 22c0 7.6 9.6 17 9.6 17S115.2 29.6 115.2 22a9.6 9.6 0 1 0-19.2 0Z"
        stroke="#141414"
        strokeWidth="1.2"
        strokeLinejoin="round"
      />
      <circle cx="105.6" cy="22" r="3.2" fill="#141414" />
    </svg>
  );
}

function InterviewArt() {
  return (
    <svg width="120" height="98" viewBox="0 0 120 98" fill="none">
      {/* 对话气泡 */}
      <path
        d="M28 12h44a12 12 0 0 1 12 12v14a12 12 0 0 1-12 12H44l-13 11 2-11h-5a12 12 0 0 1-12-12V24a12 12 0 0 1 12-12Z"
        stroke="#141414"
        strokeWidth="1.2"
        strokeLinejoin="round"
      />
      {/* 声波：高低错落，中间一根实心 */}
      <path d="M36 28v10M46 22v20M66 30v6" stroke="#141414" strokeWidth="1.4" strokeLinecap="round" />
      <rect x="55" y="26" width="2.4" height="12" rx="1.2" fill="#141414" />
      {/* 回声弧 */}
      <path d="M96 34a18 18 0 0 1 0 26" stroke="#141414" strokeWidth="1.2" strokeOpacity=".45" />
      <path d="M104 26a30 30 0 0 1 0 42" stroke="#141414" strokeWidth="1.2" strokeOpacity=".22" />
    </svg>
  );
}

const CARDS: {
  no: string;
  title: string;
  desc: string;
  route: Route;
  art: JSX.Element;
}[] = [
  {
    no: "01 / RESUME",
    title: "简历",
    desc: "解析、诊断并重写简历，把真实经历整理成有证据的表达。",
    route: "resume",
    art: <ResumeArt />,
  },
  {
    no: "02 / JOBS",
    title: "岗位",
    desc: "搜索并核验岗位，说明匹配依据与能力差距。",
    route: "jobs",
    art: <JobsArt />,
  },
  {
    no: "03 / INTERVIEW",
    title: "面试",
    desc: "结合简历与岗位 JD 进行多轮模拟面试，给到具体反馈。",
    route: "interview",
    art: <InterviewArt />,
  },
];

export default function Home({ go }: { go: (r: Route) => void }) {
  const { user, setUser } = useProfile();
  const [loginOpen, setLoginOpen] = useState(false);

  return (
    <div className="screen">
      <Ticks />
      <div className="gridlines" />

      <header className="topbar">
        <button className="logo" onClick={() => go("intro")} aria-label="重播开场">
          <Logo withWord />
        </button>
        <UserBlock
          name={user?.name}
          onOpen={() => (user ? go("archive") : setLoginOpen(true))}
        />
      </header>

      <main className="home-main">
        <div className="overline">AI Job Hunter · 求职决策与执行平台</div>
        <div className="home-mark">
          <Wordmark size="md" top="Welcome to" main="Job Hunter" />
        </div>
        <div className="tagline">
          <i />
          <span>Hunt job, hunt your heart</span>
          <i />
        </div>

        <div className="home-cards">
          {CARDS.map((c, i) => (
            <div
              className="card-wrap fade-in"
              key={c.no}
              style={{ animationDelay: `${0.12 + i * 0.09}s` }}
            >
              <article
                className="card"
                role="button"
                tabIndex={0}
                onClick={() => go(c.route)}
                onKeyDown={(e) => {
                  if (e.key === "Enter") go(c.route);
                }}
              >
                <div className="no">{c.no}</div>
                <div className="art">{c.art}</div>
                <h3>{c.title}</h3>
                <p>{c.desc}</p>
                <div className="go">进入 →</div>
                <span className="card-fold" aria-hidden="true" />
              </article>
            </div>
          ))}
        </div>
      </main>

      <footer className="meta">
        <span>AI Job Hunter / 2026</span>
        <span>简历 · 岗位 · 面试</span>
      </footer>

      <Edge side="left" label="上传资料" onClick={() => go("upload")} />
      <Edge side="right" label="查看匹配档案" onClick={() => go("archive")} />

      <LoginModal
        open={loginOpen}
        onClose={() => setLoginOpen(false)}
        onDone={(name) => {
          setUser({ name });
          setLoginOpen(false);
        }}
      />
    </div>
  );
}
