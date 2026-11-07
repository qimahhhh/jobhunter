import type { Profile } from "./types";

export type Verify = "ok" | "pending" | "dead";

export type Req = {
  label: string;
  type: "hard" | "skill" | "evidence";
};

export type Job = {
  id: string;
  company: string;
  title: string;
  city: string;
  salary: string;
  employment: string;
  education: string;
  source: string;
  verify: Verify;
  collected: string;
  reqs: Req[];
};

export const JOBS: Job[] = [
  {
    id: "j1",
    company: "字节跳动",
    title: "前端开发实习生",
    city: "上海 徐汇",
    salary: "200–300 / 天",
    employment: "实习",
    education: "本科及以上",
    source: "实习僧",
    verify: "ok",
    collected: "2 天前",
    reqs: [
      { label: "城市 上海", type: "hard" },
      { label: "类型 实习", type: "hard" },
      { label: "学历 本科", type: "hard" },
      { label: "React / TypeScript", type: "skill" },
      { label: "组件库搭建", type: "skill" },
      { label: "性能优化", type: "evidence" },
      { label: "团队协作证明", type: "evidence" },
    ],
  },
  {
    id: "j2",
    company: "小红书",
    title: "Web 前端实习生",
    city: "上海 黄浦",
    salary: "180–250 / 天",
    employment: "实习",
    education: "本科及以上",
    source: "企业官网",
    verify: "ok",
    collected: "4 小时前",
    reqs: [
      { label: "城市 上海", type: "hard" },
      { label: "类型 实习", type: "hard" },
      { label: "React", type: "skill" },
      { label: "移动端适配", type: "evidence" },
    ],
  },
  {
    id: "j3",
    company: "米哈游",
    title: "前端开发（校招）",
    city: "上海 徐汇",
    salary: "20–30K",
    employment: "校招",
    education: "本科及以上",
    source: "Offer先生",
    verify: "dead",
    collected: "6 天前",
    reqs: [
      { label: "城市 上海", type: "hard" },
      { label: "类型 校招", type: "hard" },
      { label: "图形学基础", type: "evidence" },
    ],
  },
  {
    id: "j4",
    company: "哔哩哔哩",
    title: "前端实习生",
    city: "杭州 滨江",
    salary: "150–220 / 天",
    employment: "实习",
    education: "本科及以上",
    source: "实习僧",
    verify: "pending",
    collected: "1 天前",
    reqs: [
      { label: "城市 杭州", type: "hard" },
      { label: "类型 实习", type: "hard" },
      { label: "Vue / React", type: "skill" },
      { label: "内容社区经验", type: "evidence" },
    ],
  },
];

function hardMet(label: string, p: Profile, job: Job): boolean {
  if (label.startsWith("城市")) {
    return !p.target.city || job.city.includes(p.target.city);
  }
  if (label.startsWith("类型")) {
    return !p.target.employment || job.employment === p.target.employment;
  }
  return true; // 学历默认满足
}

const NEEDS = {
  skill: (p: Profile) => p.projects.length > 0 || !!p.resume,
  evidence: (p: Profile) => p.stories.trim().length > 0,
};

export type Match = {
  met: string[];
  gap: string[];
  fail: string[];
  score: number;
};

/**
 * 匹配分不是后端算的，是拿档案里「有没有东西」推出来的假规则：
 * 有项目 -> 技能项满足；有经历 -> 证据项满足；城市对不上 -> 硬性不满足。
 * 接后端后换成 API 返回的 dimensions[]。
 */
export function matchOf(job: Job, p: Profile): Match {
  const met: string[] = [];
  const gap: string[] = [];
  const fail: string[] = [];

  for (const r of job.reqs) {
    if (r.type === "hard") {
      if (hardMet(r.label, p, job)) met.push(r.label);
      else fail.push(r.label);
    } else if (NEEDS[r.type](p)) {
      met.push(r.label);
    } else {
      gap.push(r.label);
    }
  }

  const hard = job.reqs.filter((r) => r.type === "hard");
  const hardMetCount = hard.filter((r) => met.includes(r.label)).length;
  const softMet = met.length - hardMetCount;

  const base =
    40 +
    hardMetCount * 6 +
    softMet * 7 -
    gap.length * 5 -
    fail.length * 9 +
    (hardMetCount === hard.length ? 6 : -6);
  const score = Math.max(38, Math.min(96, base));

  return { met, gap, fail, score };
}

export function sortedJobs(p: Profile): { job: Job; match: Match }[] {
  // 失效岗位一律沉底：用户看到的第一条不该是一个已经关掉的岗位。
  // 已核验 / 待核验视为同一档，档内按匹配分排。
  const tier = (v: Job["verify"]) => (v === "dead" ? 1 : 0);

  return JOBS.map((job) => ({ job, match: matchOf(job, p) })).sort(
    (a, b) => tier(a.job.verify) - tier(b.job.verify) || b.match.score - a.match.score
  );
}
