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
 * `missingInformation` 来自后端抽取返回的信息缺口，不再是一套固定题目。
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

  // 后端抽取标出的信息缺口：期望城市、可实习时长这类简历里没写清的内容
  (p.missingInformation ?? []).slice(0, 4).forEach((item, i) => {
    const label = item.replace(/[。.!！?？]+$/, "").trim();
    if (!label) return;
    qs.push({
      id: `missing-${i}`,
      tag: "待确认",
      title: `${label}？`,
      basis: "简历里没有明确写这一项，模型把它标成了信息缺口。",
      options: ["暂时不确定", "跳过这条"],
      placeholder: "直接补充，例如「上海，可实习 3 个月」",
    });
  });

  if (p.resume) {
    qs.push({
      id: "resume-period",
      tag: "简历",
      title: "简历里的时间信息都准确吗？",
      basis: `解析「${p.resume.name}」时只拿到了文件名和页数，具体起止时间需要你确认。`,
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

  // 档案信息比较全时，至少留一道补充题，避免只问一题就结束
  if (qs.length < 2) {
    qs.push({
      id: "extra",
      tag: "补充",
      title: "简历之外，还有哪段经历值得写进去？",
      basis: "生成简历只能使用档案里的内容，这一段可以补上简历没覆盖的部分。",
      options: ["没有更多了", "有一个项目", "有一段实习"],
      placeholder: "一句话：做了什么、结果如何",
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

  return qs.slice(0, 10);
}
