import type { Job } from "./jobs";
import type { Profile } from "./types";

export type IQuestion = {
  id: string;
  point: string;
  text: string;
  follow?: string;
};

/**
 * 题目从「档案 + 岗位」两边生成：项目深挖来自项目，技术题来自岗位要求。
 * 接后端后换成 Interview Agent 返回的问题。
 */
export function buildInterview(p: Profile, job: Job): IQuestion[] {
  const qs: IQuestion[] = [];

  p.projects.forEach((proj) => {
    qs.push({
      id: `proj-${proj.id}`,
      point: "项目深挖",
      text: `「${proj.name}」里最难的一个技术决定是什么？为什么这么选？`,
      follow: "如果重来一次，你会怎么做？",
    });
  });

  if (p.stories.trim()) {
    qs.push({
      id: "story",
      point: "经历与结果",
      text: "你写的那段经历，最后的结果是怎么量化出来的？",
      follow: "这个数字是怎么测的？有对比基线吗？",
    });
  }

  job.reqs
    .filter((r) => r.type !== "hard")
    .forEach((r, i) => {
      qs.push({
        id: `req-${i}`,
        point: r.label,
        text: `「${r.label}」这块你怎么理解？在项目里具体怎么用的？`,
        follow: i % 2 === 0 ? "如果没有现成方案，你会怎么做？" : undefined,
      });
    });

  if (qs.length < 3) {
    qs.push({
      id: "fallback",
      point: "基础",
      text: "介绍一下你自己，以及为什么想做前端。",
    });
  }

  return qs.slice(0, 8);
}
