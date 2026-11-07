import type { Profile } from "./types";

export type Question = {
  id: string;
  tag: string;
  title: string;
  basis: string;
  options: string[];
  placeholder: string;
};

/**
 * 题量由档案动态决定：项目越多、缺证据的地方越多，问题越多。
 * 这里是前端 mock 规则，接后端后换成接口返回的 questions[]。
 */
export function buildQuestions(p: Profile): Question[] {
  const qs: Question[] = [];

  p.projects.forEach((proj, i) => {
    qs.push({
      id: `proj-${proj.id}`,
      tag: `项目 ${i + 1}`,
      title: `「${proj.name}」这个项目里，你具体负责哪一部分？`,
      basis: `你的档案里只有项目名「${proj.name}」，没有说明是你独立完成还是与人协作。`,
      options: ["独立完成", "与人协作", "只做了其中一块"],
      placeholder: "也可以直接写，比如「负责上传页和简历编辑器的交互」",
    });
  });

  if (p.resume) {
    qs.push({
      id: "resume-period",
      tag: "简历",
      title: "简历上的实习时间是 2024.07 – 2024.09，对吗？",
      basis: `从「${p.resume.name}」识别出 1 段实习，但起止时间只精确到月份。`,
      options: ["对，就是这样", "不是，我改一下"],
      placeholder: "需要的话，写上准确的时间范围",
    });
  }

  if (!p.stories.trim()) {
    qs.push({
      id: "stories",
      tag: "经历",
      title: "你最能代表自己的一段经历是什么？",
      basis: "档案里的「主观经历」还是空的，这部分没法从文件里读出来。",
      options: ["不太确定怎么写", "先跳过这部分"],
      placeholder: "一句话就行：做了什么、遇到什么、最后怎样",
    });
  }

  if (!qs.length) {
    qs.push({
      id: "fallback",
      tag: "档案",
      title: "先说说你最近在做的一件事？",
      basis: "档案里暂时没有足够的内容，这条会帮后面生成简历时有个起点。",
      options: ["写一句", "跳过"],
      placeholder: "例如：最近在做一个求职网站的前端",
    });
  }

  return qs.slice(0, 8);
}
