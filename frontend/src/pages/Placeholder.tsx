import Ticks from "../components/Ticks";
import type { Route } from "../App";

type Props = {
  title: string;
  onBack: () => void;
  go: (r: Route) => void;
};

export default function Placeholder({ title, onBack }: Props) {
  return (
    <div className="screen">
      <Ticks />
      <div className="gridlines" />
      <header className="topbar">
        <button className="back" onClick={onBack}>
          ← 返回主页
        </button>
      </header>
      <main className="ph-main">
        <div className="overline">In progress</div>
        <h1 className="ph-title">{title}</h1>
        <p className="ph-note">这一页的线稿和关键帧已经定稿，实现排在这一轮之后。</p>
      </main>
    </div>
  );
}
