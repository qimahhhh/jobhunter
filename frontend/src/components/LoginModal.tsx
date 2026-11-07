import { useEffect, useRef, useState } from "react";

type Props = {
  open: boolean;
  onClose: () => void;
  onDone: (name: string) => void;
};

export default function LoginModal({ open, onClose, onDone }: Props) {
  const [tab, setTab] = useState<"login" | "register">("login");
  const [account, setAccount] = useState("");
  const [code, setCode] = useState("");
  const boxRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    window.addEventListener("keydown", onKey);
    const prev = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    return () => {
      window.removeEventListener("keydown", onKey);
      document.body.style.overflow = prev;
    };
  }, [open, onClose]);

  if (!open) return null;

  const submit = () => {
    if (!account.trim()) return;
    onDone("李思远");
  };

  return (
    <div className="scrim" onMouseDown={onClose}>
      <div
        className="modal"
        role="dialog"
        aria-modal="true"
        aria-labelledby="auth-title"
        ref={boxRef}
        onMouseDown={(e) => e.stopPropagation()}
      >
        <button className="modal-x" aria-label="关闭" onClick={onClose}>
          <svg width="13" height="13" viewBox="0 0 13 13" fill="none">
            <path d="M1 1l11 11M12 1L1 12" stroke="currentColor" strokeWidth="1.2" />
          </svg>
        </button>

        <div className="eyebrow">Account</div>
        <h2 id="auth-title">{tab === "login" ? "登录 Job Hunter" : "注册 Job Hunter"}</h2>
        <p className="sub">登录后可上传简历与项目资料，建立你的求职档案。</p>

        <div className="auth-tabs">
          <button className={tab === "login" ? "on" : ""} onClick={() => setTab("login")}>
            登录
          </button>
          <button className={tab === "register" ? "on" : ""} onClick={() => setTab("register")}>
            注册
          </button>
        </div>

        <label className="field-label">手机号 / 邮箱</label>
        <input
          className="field"
          autoFocus
          value={account}
          placeholder="you@example.com"
          onChange={(e) => setAccount(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter") submit();
          }}
        />

        <label className="field-label">验证码</label>
        <div className="field code-row">
          <input
            value={code}
            placeholder="6 位数字验证码"
            onChange={(e) => setCode(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter") submit();
            }}
          />
          <button className="code-btn">获取验证码</button>
        </div>

        <button className="btn primary auth-submit" disabled={!account.trim()} onClick={submit}>
          进入 Job Hunter
        </button>

        <div className="or">或</div>
        <div className="oauth">
          <button>微信登录</button>
          <button>GitHub 登录</button>
        </div>
        <p className="fine">继续即表示同意《服务条款》与《隐私政策》</p>
      </div>
    </div>
  );
}
