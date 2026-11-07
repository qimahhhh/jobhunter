type Props = {
  size?: "lg" | "md";
  top?: string;
  main?: string;
};

/**
 * 字标：上层轻、字距极宽；下层重、字距收紧。
 * 用字重和字距做层级，不用描边——描边在大字号下会显得廉价。
 */
export default function Wordmark({ size = "lg", top = "Job", main = "Hunter" }: Props) {
  return (
    <h1 className={`wm wm-${size}`}>
      <span className="wm-top">{top}</span>
      <span className="wm-main">{main}</span>
    </h1>
  );
}
