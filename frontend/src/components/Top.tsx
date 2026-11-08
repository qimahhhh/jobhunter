import type { ReactNode } from "react";

type Props = {
  right?: ReactNode;
  onHome?: () => void;
  intro?: () => void;
  back?: { label: string; onClick: () => void };
};

export default function Top({ right, onHome, intro, back }: Props) {
  return (
    <header className="top">
      <div className="row" style={{ gap: 18 }}>
        <button className="brand" onClick={onHome} aria-label="回到功能页首页" type="button">
          <span className="brand-mark" aria-hidden="true" />
          Job Hunter
        </button>
        {intro && (
          <button className="linkish" onClick={intro} type="button">
            ← 开场
          </button>
        )}
        {back && (
          <button className="linkish" onClick={back.onClick} type="button">
            ← {back.label}
          </button>
        )}
      </div>
      <div className="top-r">{right}</div>
    </header>
  );
}
