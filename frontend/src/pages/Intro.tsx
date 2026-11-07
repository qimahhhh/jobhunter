import { useEffect, useRef } from "react";
import Ticks from "../components/Ticks";
import UserBlock from "../components/UserBlock";
import Logo from "../components/Logo";
import Wordmark from "../components/Wordmark";

type Props = {
  onEnter: () => void;
};

export default function Intro({ onEnter }: Props) {
  const fired = useRef(false);
  const enter = useRef(onEnter);
  enter.current = onEnter;

  // 只触发一次：滚轮、触摸、键盘、点击都走这里
  const go = () => {
    if (fired.current) return;
    fired.current = true;
    enter.current();
  };

  useEffect(() => {
    let startY = 0;

    const onWheel = (e: WheelEvent) => {
      if (Math.abs(e.deltaY) > 6) go();
    };
    const onKey = (e: KeyboardEvent) => {
      if (["ArrowDown", "PageDown", " ", "Enter"].includes(e.key)) {
        e.preventDefault();
        go();
      }
    };
    const onTouchStart = (e: TouchEvent) => {
      startY = e.touches[0]?.clientY ?? 0;
    };
    const onTouchMove = (e: TouchEvent) => {
      const y = e.touches[0]?.clientY ?? 0;
      if (startY - y > 40) go();
    };

    window.addEventListener("wheel", onWheel, { passive: true });
    window.addEventListener("keydown", onKey);
    window.addEventListener("touchstart", onTouchStart, { passive: true });
    window.addEventListener("touchmove", onTouchMove, { passive: true });

    return () => {
      window.removeEventListener("wheel", onWheel);
      window.removeEventListener("keydown", onKey);
      window.removeEventListener("touchstart", onTouchStart);
      window.removeEventListener("touchmove", onTouchMove);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  return (
    <div
      className="screen intro"
      onClick={go}
      role="button"
      tabIndex={0}
      aria-label="进入主页"
    >
      <Ticks />

      <div className="intro-corner tl fade-in" style={{ animationDelay: "0.7s" }}>
        <Logo size={26} />
      </div>
      <div className="intro-corner tr fade-in" style={{ animationDelay: "0.8s" }}>
        <UserBlock onOpen={go} />
      </div>

      <div className="intro-center">
        <div className="intro-mark">
          <Logo size={30} />
        </div>
        <Wordmark size="lg" />
      </div>

      <div className="scroll-hint fade-in" style={{ animationDelay: "1.25s" }}>
        <span className="mouse" />
        <span className="tx">向下滑动</span>
      </div>
    </div>
  );
}
