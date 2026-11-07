type Props = {
  name?: string;
  onOpen: () => void;
};

export default function UserBlock({ name, onOpen }: Props) {
  return (
    <button
      className={name ? "account is-logged" : "account"}
      onClick={onOpen}
      aria-label={name ? "账户" : "登录 / 注册"}
    >
      {name ? (
        <>
          <span className="acc-name">{name}</span>
          <span className="acc-avatar">{name.slice(0, 1)}</span>
        </>
      ) : (
        <span className="acc-login">登录</span>
      )}
    </button>
  );
}
