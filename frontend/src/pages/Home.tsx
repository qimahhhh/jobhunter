import { useState } from "react";
import Top from "../components/Top";
import Band from "../components/Band";
import UserBlock from "../components/UserBlock";
import LoginModal from "../components/LoginModal";
import { useProfile } from "../store";
import type { Route } from "../App";

const DESTS: {
  no: string;
  name: string;
  sub: string;
  route: Route;
}[] = [
  {
    no: "01",
    name: "简历",
    sub: "解析、诊断并重写——把经历整理成有证据的表达",
    route: "resume",
  },
  {
    no: "02",
    name: "岗位",
    sub: "核验是否仍在招——说明每一条匹配依据与缺口",
    route: "jobs",
  },
  {
    no: "03",
    name: "面试",
    sub: "按你的简历与 JD 追问——给到可以改的具体反馈",
    route: "interview",
  },
];

export default function Home({ go }: { go: (r: Route) => void }) {
  const { setUser } = useProfile();
  const [loginOpen, setLoginOpen] = useState(false);

  return (
    <div className="shell" id="main">
      <Top
        intro={() => go("intro")}
        onHome={() => go("home")}
        right={
          <UserBlock
            onLogin={() => setLoginOpen(true)}
            go={go}
          />
        }
      />

      <main className="page tight">
        <div className="eyebrow">现场导视 / 今天先解决哪一步</div>
        <h1 className="q mt-16">今天先解决哪一步？</h1>
        <p className="lead">
          三块展区，一条动线。选一个入口，剩下的它会告诉你怎么走。
        </p>

        <div className="mt-48">
          {DESTS.map((d) => (
            <button
              key={d.no}
              className="dest"
              onClick={() => go(d.route)}
              type="button"
            >
              <span className="dest-no">{d.no}</span>
              <span className="dest-body">
                <span className="dest-name">{d.name}</span>
                <span className="dest-sub">{d.sub}</span>
              </span>
              <span className="dest-go" aria-hidden="true">
                →
              </span>
            </button>
          ))}
        </div>
      </main>

      <Band
        step={0}
        total={4}
        label="当前位置 · 还没有开始"
        action={{ label: "从简历开始 →", onClick: () => go("resume") }}
      />

      <LoginModal
        open={loginOpen}
        onClose={() => setLoginOpen(false)}
        onDone={(name, account) => {
          setUser({ name, account });
        }}
        onNext={() => {
          setLoginOpen(false);
          go("upload");
        }}
      />
    </div>
  );
}
