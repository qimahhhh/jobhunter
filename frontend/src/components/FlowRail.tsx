import type { ReactNode } from "react";

export type StepState = "done" | "now" | "next";

export type Step = {
  label: string;
  state: StepState;
  sub?: string;
};

type Props = {
  steps: Step[];
  children?: ReactNode;
};

export default function FlowRail({ steps, children }: Props) {
  return (
    <aside className="flow">
      <div className="cap">Process</div>
      <ul className="steps">
        {steps.map((s) => (
          <li key={s.label} className={s.state === "next" ? undefined : s.state}>
            {s.label}
            {s.sub && <span className="st">{s.sub}</span>}
          </li>
        ))}
      </ul>
      {children}
    </aside>
  );
}
