type Props = {
  side: "left" | "right";
  label: string;
  onClick: () => void;
};

export default function Edge({ side, label, onClick }: Props) {
  return (
    <button className={`edge ${side}`} aria-label={label} onClick={onClick}>
      {side === "left" ? (
        <svg width="15" height="18" viewBox="0 0 15 18" fill="none">
          <path d="M7.5 16.5V2.6" stroke="currentColor" strokeWidth="1.2" />
          <path d="M3.4 6.6 7.5 2.5l4.1 4.1" stroke="currentColor" strokeWidth="1.2" />
        </svg>
      ) : (
        <svg width="16" height="18" viewBox="0 0 16 18" fill="none">
          <rect x="1" y="1" width="14" height="16" rx="2" stroke="currentColor" strokeWidth="1.2" />
          <path d="M4.4 5.6h7.2M4.4 9h7.2M4.4 12.4h4.2" stroke="currentColor" strokeWidth="1.2" />
        </svg>
      )}
    </button>
  );
}
