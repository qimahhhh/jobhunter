import { useEffect, useRef, useState } from "react";

const GLYPHS = "ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789#%&@$";

type Props = {
  text: string;
  delay?: number;
  step?: number;
};

/**
 * 翻牌字：字母先乱码翻动，再逐个落定。
 * 致敬机场翻牌显示牌，也是这套视觉的原生动画。
 */
export default function FlipWord({ text, delay = 0, step = 68 }: Props) {
  const target = text.split("");
  const [shown, setShown] = useState<string[]>(() => target.map(() => " "));
  const [settled, setSettled] = useState(false);
  const raf = useRef(0);

  useEffect(() => {
    const reduce =
      typeof window !== "undefined" &&
      window.matchMedia("(prefers-reduced-motion: reduce)").matches;

    if (reduce) {
      setShown(target);
      setSettled(true);
      return;
    }

    const t0 = performance.now() + delay;
    const at = target.map((_, i) => t0 + 340 + i * step);
    const last = at[at.length - 1] ?? t0;
    let prev = 0;

    const tick = (now: number) => {
      // 约 30fps 就够，翻牌本来就是跳的
      if (now - prev > 33) {
        prev = now;
        setShown(
          target.map((c, i) =>
            now >= at[i] ? c : GLYPHS[Math.floor(Math.random() * GLYPHS.length)]
          )
        );
      }
      if (now < last) {
        raf.current = requestAnimationFrame(tick);
      } else {
        setShown(target);
        setSettled(true);
      }
    };

    raf.current = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(raf.current);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [text, delay, step]);

  return (
    <span className={settled ? "flip is-settled" : "flip"} aria-label={text}>
      {shown.map((c, i) => (
        <span className="fl" key={i} aria-hidden="true">
          {c === " " ? "\u00A0" : c}
        </span>
      ))}
    </span>
  );
}
