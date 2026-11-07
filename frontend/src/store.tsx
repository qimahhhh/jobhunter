import { createContext, useContext, useMemo, useState, type ReactNode } from "react";
import { EMPTY_PROFILE, type InterviewResult, type Profile } from "./types";

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
  const [profile, setProfile] = useState<Profile>(EMPTY_PROFILE);
  const [interview, setInterview] = useState<InterviewResult | null>(null);
  const [compare, setCompare] = useState<string[]>([]);
  const [user, setUser] = useState<{ name: string } | null>(null);

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
