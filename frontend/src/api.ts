import type { Job } from "./jobs";
import type { Profile } from "./types";

const configured = import.meta.env.VITE_API_BASE ?? "http://127.0.0.1:8000";

/** 后端地址：本地默认 8000，部署时用 VITE_API_BASE 覆盖。 */
export const API_BASE = configured.replace(/\/+$/, "");

export class ApiError extends Error {
  readonly status: number;

  constructor(status: number, message: string) {
    super(message);
    this.name = "ApiError";
    this.status = status;
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`, init);
  if (!res.ok) {
    let detail = `${res.status} ${res.statusText}`;
    try {
      const data: unknown = await res.json();
      if (data && typeof data === "object" && "detail" in data) {
        const value = (data as { detail: unknown }).detail;
        detail = typeof value === "string" ? value : JSON.stringify(value);
      }
    } catch {
      // 非 JSON 错误体：保留状态码和状态文本
    }
    throw new ApiError(res.status, detail);
  }
  return (await res.json()) as T;
}

/* ---------- 简历抽取 ---------- */

export type ExtractedProfile = {
  summary: string;
  skills: string[];
  experiences: string[];
};

export type ExtractionResult = {
  profile: ExtractedProfile | null;
  evidence: string[];
  unresolved_evidence: string[];
  chunk_ids: string[];
  degraded: boolean;
  notes: string[];
};

export function extractResume(file: File): Promise<ExtractionResult> {
  return request<ExtractionResult>(
    `/api/v1/profiles/extract/file?filename=${encodeURIComponent(file.name)}`,
    {
      method: "POST",
      headers: { "Content-Type": "application/octet-stream" },
      body: file,
    }
  );
}

/* ---------- 岗位匹配 ---------- */

export type InterviewQuestion = {
  type: string;
  question: string;
  why: string;
};

export type JobFit = {
  /** 0–100 的展示分，后端原始值是 0–1 */
  score: number;
  matchPoints: string[];
  gaps: string[];
  recommendation: string;
  summary: string;
  confidence: number;
  interview: InterviewQuestion[];
  suggestions: string[];
  warnings: string[];
};

type JobFitResponse = {
  request_id: string;
  fit_report: {
    score: number;
    match_points: string[];
    gaps: string[];
    recommendation: string;
    confidence: number;
    summary: string;
  };
  resume_suggestions: string[];
  interview_questions: InterviewQuestion[];
  warnings: string[];
};

type EmploymentType = "internship" | "part_time" | "full_time" | "contract";

const EMPLOYMENT: Record<string, EmploymentType> = {
  实习: "internship",
  校招: "full_time",
  社招: "full_time",
};

function toProfileInput(profile: Profile) {
  const skills = profile.skills?.length
    ? profile.skills
    : profile.projects.map((project) => project.name);
  const experiences = [
    ...(profile.stories.trim() ? [profile.stories.trim()] : []),
    ...profile.projects.map((project) => `项目：${project.name}`),
  ];
  const summary =
    [
      profile.summary,
      profile.target.role,
      profile.target.city,
      profile.target.employment ? `求职类型 ${profile.target.employment}` : "",
    ]
      .filter((value): value is string => !!value && value.trim().length > 0)
      .join("；") || "求职者档案";

  return { summary, skills, experiences };
}

function toJobInput(job: Job) {
  return {
    title: job.title,
    company: job.company,
    description: [
      job.company,
      job.title,
      job.city,
      job.salary,
      job.education,
      job.employment,
      job.source,
    ].join(" "),
    requirements: job.reqs.map((req) => req.label).join("\n"),
    employment_type: EMPLOYMENT[job.employment] ?? "full_time",
    source_name: job.source,
  };
}

export async function fitJob(profile: Profile, job: Job): Promise<JobFit> {
  const data = await request<JobFitResponse>("/api/v1/job-fit", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ profile: toProfileInput(profile), job: toJobInput(job) }),
  });

  return {
    score: Math.round(data.fit_report.score * 100),
    matchPoints: data.fit_report.match_points,
    gaps: data.fit_report.gaps,
    recommendation: data.fit_report.recommendation,
    summary: data.fit_report.summary,
    confidence: data.fit_report.confidence,
    interview: data.interview_questions,
    suggestions: data.resume_suggestions,
    warnings: data.warnings,
  };
}
