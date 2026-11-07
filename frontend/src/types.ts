export type ResumeFile = {
  name: string;
  size: number;
  pages: number;
  experiences: number;
};

export type ProjectSource = "github" | "zip";

export type Project = {
  id: string;
  name: string;
  source: ProjectSource;
  fileCount: number;
  isMain: boolean;
};

export type Target = {
  role?: string;
  city?: string;
  employment?: "实习" | "校招" | "社招";
};

export type Profile = {
  resume: ResumeFile | null;
  projects: Project[];
  stories: string;
  target: Target;
  /** 简历问答里已确认的答案：questionId -> 回答 */
  answers: Record<string, string>;
  /** 后端简历解析得到的摘要 / 技能 / 证据（可选） */
  summary?: string;
  skills?: string[];
  evidence?: string[];
  extraction?: { degraded: boolean; notes: string[] };
};

/** 面试结果：答题记录 + 用时，报告页从这里推导 */
export type InterviewAnswer = {
  id: string;
  point: string;
  text: string;
};

export type InterviewResult = {
  jobId: string;
  answers: InterviewAnswer[];
  seconds: number;
};

export const EMPTY_PROFILE: Profile = {
  resume: null,
  projects: [],
  stories: "",
  target: {},
  answers: {},
};

/** 六项完成度：只有前三项能在上传页填，后三项来自岗位页 */
export type ChecklistItem = {
  key: string;
  label: string;
  done: boolean;
  where?: "jobs";
};

export function checklist(p: Profile): ChecklistItem[] {
  return [
    { key: "resume", label: "个人简历", done: !!p.resume },
    { key: "role", label: "目标岗位", done: !!p.target.role, where: "jobs" },
    { key: "city", label: "目标城市", done: !!p.target.city, where: "jobs" },
    { key: "projects", label: "项目经历", done: p.projects.length > 0 },
    { key: "stories", label: "主观经历", done: p.stories.trim().length > 0 },
    { key: "employment", label: "期望类型", done: !!p.target.employment, where: "jobs" },
  ];
}
