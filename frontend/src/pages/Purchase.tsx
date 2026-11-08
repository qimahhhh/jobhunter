import Top from "../components/Top";
import Band from "../components/Band";
import { useProfile } from "../store";
import type { Route } from "../App";

const INCLUDED = [
  "五项评分的依据，以及每一项怎么改",
  "薄弱点清单：缺什么、下次怎么答",
  "每道题的追问记录与提示",
  "一页可导出的报告，截图就能带走",
];

export default function Purchase({ go }: { go: (r: Route) => void }) {
  const { unlocked, setUnlocked } = useProfile();

  return (
    <div className="shell" id="main">
      <Top
        onHome={() => go("home")}
        back={{ label: "返回报告", onClick: () => go("report") }}
      />

      <main className="page">
        <div className="eyebrow">完整报告 · 一次购买</div>
        <h1 className="h1 mt-16">解锁完整面试报告</h1>
        <p className="lead">评分只是结论。改法、薄弱点、每道题的记录，都在完整报告里。</p>

        <div className="buy mt-32">
          <div>
            <div className="buy-price num">19</div>
            <div className="buy-unit">元 / 一份报告</div>
            <button
              className="pill solid mt-24"
              type="button"
              onClick={() => {
                setUnlocked(true);
                go("report");
              }}
            >
              {unlocked ? "已解锁，回到报告 →" : "购买并解锁 →"}
            </button>
            <p className="small mt-8">演示环境不接支付，点一下即解锁。</p>
          </div>

          <ul className="buy-list">
            {INCLUDED.map((t) => (
              <li key={t}>{t}</li>
            ))}
          </ul>
        </div>
      </main>

      <Band step={4} total={4} label="购买 · 完整报告" />
    </div>
  );
}
