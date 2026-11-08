import { useState, type FormEvent } from "react";

type Props = {
  onDone: (name: string, account: string) => void;
  onNext: () => void;
  nextLabel?: string;
};

export default function AuthForm({ onDone, onNext, nextLabel = "去填档案 →" }: Props) {
  const [tab, setTab] = useState<"login" | "register">("login");
  const [name, setName] = useState("");
  const [email, setEmail] = useState("");
  const [code, setCode] = useState("");
  const [done, setDone] = useState<{ name: string; account: string; register: boolean } | null>(null);

  const ready = !!email.trim() && !!code.trim() && (tab === "login" || !!name.trim());

  const submit = (e: FormEvent) => {
    e.preventDefault();
    if (!ready) return;
    const who = tab === "register" ? name.trim() : name.trim() || "rael";
    const account = email.trim();
    onDone(who, account);
    setDone({ name: who, account, register: tab === "register" });
  };

  if (done) {
    return (
      <div className="auth-done">
        <div className="eyebrow">已完成</div>
        <p className="h3 mt-8">
          {done.register ? "注册成功" : "登录成功"}，{done.name}
        </p>
        <p className="small mt-8">{done.account}</p>
        <button className="pill solid mt-24" onClick={onNext} type="button">
          {nextLabel}
        </button>
      </div>
    );
  }

  return (
    <form className="auth" onSubmit={submit} noValidate>
      <div className="auth-tabs" role="tablist" aria-label="登录或注册">
        <button
          role="tab"
          aria-selected={tab === "login"}
          className={tab === "login" ? "on" : ""}
          onClick={() => setTab("login")}
          type="button"
        >
          登录
        </button>
        <button
          role="tab"
          aria-selected={tab === "register"}
          className={tab === "register" ? "on" : ""}
          onClick={() => setTab("register")}
          type="button"
        >
          注册
        </button>
      </div>

      <div className="auth-grid">
        {tab === "register" && (
          <label className="field">
            <span>姓名</span>
            <input
              value={name}
              autoComplete="name"
              placeholder="你的名字"
              onChange={(e) => setName(e.target.value)}
            />
          </label>
        )}

        <label className="field">
          <span>邮箱</span>
          <input
            value={email}
            inputMode="email"
            autoComplete="email"
            placeholder="you@example.com"
            onChange={(e) => setEmail(e.target.value)}
          />
        </label>

        <label className="field">
          <span>验证码</span>
          <div className="row" style={{ gap: 8 }}>
            <input
              value={code}
              inputMode="numeric"
              placeholder="6 位验证码"
              onChange={(e) => setCode(e.target.value)}
            />
            <button className="pill sm nowrap" type="button">
              获取验证码
            </button>
          </div>
        </label>
      </div>

      <button className="pill solid mt-24" type="submit" disabled={!ready}>
        {tab === "login" ? "登录" : "注册并进入"}
      </button>
    </form>
  );
}
