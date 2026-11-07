type Props = {
  withWord?: boolean;
  size?: number;
};

/**
 * 标志：一个准星（hunter = 瞄准），单线、和页面其它图形同一套笔触。
 * 不用字母 J 是因为它和标题里的 "Job" 重复，且单字母撑不起左上角。
 */
export default function Logo({ withWord = false, size = 22 }: Props) {
  return (
    <span className="brand">
      <svg
        width={size}
        height={size}
        viewBox="0 0 22 22"
        fill="none"
        aria-hidden="true"
        className="brand-mark"
      >
        <circle cx="11" cy="11" r="8.2" stroke="currentColor" strokeWidth="1.3" />
        <circle cx="11" cy="11" r="1.9" fill="currentColor" />
        <path d="M13.4 8.6 17.6 4.4" stroke="currentColor" strokeWidth="1.3" />
        <path d="M14.6 4.4h3v3" stroke="currentColor" strokeWidth="1.3" />
      </svg>
      {withWord && <b className="brand-word">Job Hunter</b>}
    </span>
  );
}
