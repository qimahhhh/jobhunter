import { useEffect, useRef } from "react";
import AuthForm from "./AuthForm";

type Props = {
  open: boolean;
  onClose: () => void;
  onDone: (name: string, account: string) => void;
  onNext: () => void;
};

export default function LoginModal({ open, onClose, onDone, onNext }: Props) {
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
        <div className="modal-head">
          <span className="eyebrow">Account / 账户</span>
          <button className="modal-x" aria-label="关闭" onClick={onClose} type="button">
            ✕
          </button>
        </div>

        <h2 id="auth-title" className="h2">
          登录或注册
        </h2>
        <p className="small mt-8">登录后可上传简历与项目资料，建立你的求职档案。</p>

        <div className="mt-16">
          <AuthForm onDone={(name, account) => onDone(name, account)} onNext={onNext} />
        </div>

        <p className="small mt-16">继续即表示同意《服务条款》与《隐私政策》</p>
      </div>
    </div>
  );
}
