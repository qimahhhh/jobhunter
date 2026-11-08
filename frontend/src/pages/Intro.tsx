import { useEffect, useRef, useState } from "react";
import FlipWord from "../components/FlipWord";
import AuthForm from "../components/AuthForm";
import { useProfile } from "../store";
import type { Route } from "../App";

type Props = {
  onEnter: () => void;
  go: (r: Route) => void;
};

const STEPS = [
  {
    no: "01",
    title: "上传简历",
    body: "解析出技能、经历和可以引用的证据，而不是一句「熟悉 React」。",
  },
  {
    no: "02",
    title: "核对岗位",
    body: "先确认它还在招，再逐条说明命中什么、缺什么、缺口在哪一栏。",
  },
  {
    no: "03",
    title: "练一场",
    body: "按你的简历和 JD 追问，答完给一份能照着改的报告。",
  },
];

const T_YELLOW = 1150;
const T_MOVE = 1850;

let introPlayed = false;

export default function Intro({ go }: Props) {
  const { setUser } = useProfile();
  const [replay] = useState(() => introPlayed);
  const [phase, setPhase] = useState<"cold" | "move" | "done">(replay ? "done" : "cold");
  const [yellow, setYellow] = useState(replay);
  const wordRef = useRef<HTMLHeadingElement>(null);

  useEffect(() => {
    if (replay) return;
    introPlayed = true;

    const reduce = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    if (reduce) {
      setYellow(true);
      setPhase("done");
      return;
    }

    const el = wordRef.current;
    if (!el) return;

    const timers: number[] = [];
    const raf = requestAnimationFrame(() => {
      const r = el.getBoundingClientRect();
      const dx = window.innerWidth / 2 - (r.left + r.width / 2);
      const dy = window.innerHeight / 2 - (r.top + r.height / 2);
      el.style.transition = "none";
      el.style.transform = `translate(${dx}px, ${dy}px)`;
      void el.offsetWidth;
      el.style.transition = "";

      timers.push(window.setTimeout(() => setYellow(true), T_YELLOW));
      timers.push(
        window.setTimeout(() => {
          el.style.transform = "";
          setPhase("move");
        }, T_MOVE)
      );
      timers.push(window.setTimeout(() => setPhase("done"), T_MOVE + 900));
    });

    return () => {
      cancelAnimationFrame(raf);
      timers.forEach(clearTimeout);
    };
  }, [replay]);

  return (
    <div className={`shell intro${yellow ? " is-yellow" : ""}`} data-phase={phase} id="main">
      <header className="top intro-top">
        <div className="row" style={{ gap: 12 }}>
          <span className="brand-mark" aria-hidden="true" />
          <span className="mono" style={{ fontSize: 13, fontWeight: 700, letterSpacing: ".16em" }}>
            JOB HUNTER
          </span>
        </div>
      </header>

      <section className="hero">
        <div className="hero-body">
          <div className="hero-copy">
            <div className="eyebrow">求职决策与执行平台</div>
          </div>

          <h1 className="word" ref={wordRef}>
            <span className="plate">
              <FlipWord text="JOB" delay={140} />
            </span>
            <span className="plate p2">
              <FlipWord text="HUNTER" delay={430} step={62} />
            </span>
          </h1>

          <div className="hero-tail">
            <p className="lead">
              简历、岗位、面试，一条线。每屏只回答一个问题，每个结论都能翻到依据。
            </p>

            <div className="scroll-cue" aria-hidden="true">
              <span className="cue-line" />
              向下看它怎么工作
            </div>
          </div>
        </div>
      </section>

      <section className="auth-sec">
        <div className="eyebrow">登录 / 注册</div>
        <h2 className="h2 mt-8">先有账号，档案才存得住。</h2>

        <div className="auth-wrap mt-24">
          <AuthForm
            onDone={(name, account) => setUser({ name, account })}
            onNext={() => go("upload")}
          />
        </div>
      </section>

      <section className="steps">
        <div className="eyebrow">三块，一条线</div>
        <div className="grid3 mt-16">
          {STEPS.map((s) => (
            <div key={s.no}>
              <div className="num step-no">{s.no}</div>
              <h3 className="h3 mt-8">{s.title}</h3>
              <p className="small mt-8">{s.body}</p>
            </div>
          ))}
        </div>
      </section>

      <section className="enter">
        <div>
          <div className="eyebrow on-ink">还没准备好</div>
          <p className="h2 mt-8">先去看看三个板块，随时能回来。</p>
        </div>
        <button className="pill y" type="button" onClick={() => go("home")}>
          跳过，先看主页
        </button>
      </section>
    </div>
  );
}
