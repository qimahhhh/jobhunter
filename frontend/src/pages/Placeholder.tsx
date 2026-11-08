import Top from "../components/Top";
import Band from "../components/Band";
import type { Route } from "../App";

type Props = {
  title: string;
  onBack: () => void;
  go: (r: Route) => void;
};

export default function Placeholder({ onBack }: Props) {
  return (
    <div className="shell" id="main">
      <Top
        onHome={onBack}
        back={{ label: "返回主页", onClick: onBack }}
      />

      <main className="page">
        <h1 className="h1">这一页还在排期</h1>
      </main>

      <Band step={0} total={4} label="尚未排期" />
    </div>
  );
}
