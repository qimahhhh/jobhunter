import { createContext, useContext, useEffect, useMemo, useState, type ReactNode } from "react";
import { EMPTY_PROFILE, type InterviewResult, type Profile } from "./types";

const STORAGE_KEY = "jobhunter.state.v1";

type Persisted = {
  profile?: Partial<Profile>;
  interview?: InterviewResult | null;
  compare?: string[];
  user?: { name: string } | null;
};

function load(): Persisted {
  if (typeof window === "undefined") return {};
  try {
    const raw = window.localStorage.getItem(STORAGE_KEY);
    if (!raw) return {};
    const parsed: unknown = JSON.parse(raw);
    return parsed && typeof parsed === "object" ? (parsed as Persisted) : {};
  } catch {
    // 手动改坏或隐私模式禁用存储时，退回空档案
    return {};
  }
}

type Ctx = {
  profile: Profile;
  setProfile: (next: Profile) => void;
  patch: (partial: Partial<Profile>) => void;
  interview: InterviewResult | null;
  setInterview: (next: InterviewResult | null) => void;
  compare: string[];
  toggleCompare: (id: string) => void;
  user: { name: string } | null;
  setUser: (next: { name: string } | null) => void;
};

const ProfileContext = createContext<Ctx | null>(null);

export function ProfileProvider({ children }: { children: ReactNode }) {
  const [restored] = useState<Persisted>(load);
  const [profile, setProfile] = useState<Profile>(() => ({
    ...EMPTY_PROFILE,
    ...restored.profile,
    target: { ...EMPTY_PROFILE.target, ...restored.profile?.target },
  }));
  const [interview, setInterview] = useState<InterviewResult | null>(restored.interview ?? null);
  const [compare, setCompare] = useState<string[]>(restored.compare ?? []);
  const [user, setUser] = useState<{ name: string } | null>(restored.user ?? null);

  // 任何一个状态变化都写回 localStorage，刷新页面不丢
  useEffect(() => {
    try {
      const data: Persisted = { profile, interview, compare, user };
      window.localStorage.setItem(STORAGE_KEY, JSON.stringify(data));
    } catch {
      // 配额满 / 隐私模式：忽略，不影响当前会话
    }
  }, [profile, interview, compare, user]);

  const value = useMemo<Ctx>(
    () => ({
      profile,
      setProfile,
      patch: (partial) => setProfile((prev) => ({ ...prev, ...partial })),
      interview,
      setInterview,
      compare,
      toggleCompare: (id) =>
        setCompare((prev) =>
          prev.includes(id) ? prev.filter((x) => x !== id) : prev.length >= 4 ? prev : [...prev, id]
        ),
      user,
      setUser,
    }),
    [profile, interview, compare, user]
  );

  return <ProfileContext.Provider value={value}>{children}</ProfileContext.Provider>;
}

export function useProfile(): Ctx {
  const ctx = useContext(ProfileContext);
  if (!ctx) throw new Error("useProfile must be used inside <ProfileProvider>");
  return ctx;
}
