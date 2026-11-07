import { useEffect, useState } from "react";
import { ProfileProvider } from "./store";
import Intro from "./pages/Intro";
import Home from "./pages/Home";
import Upload from "./pages/Upload";
import Resume from "./pages/Resume";
import ResumeQA from "./pages/ResumeQA";
import Jobs from "./pages/Jobs";
import JobDetail from "./pages/JobDetail";
import Archive from "./pages/Archive";
import Interview from "./pages/Interview";
import Report from "./pages/Report";
import Compare from "./pages/Compare";
import ResumeDraft from "./pages/ResumeDraft";
import Placeholder from "./pages/Placeholder";

export type Route =
  | "intro"
  | "home"
  | "upload"
  | "resume"
  | "resume-qa"
  | "resume-draft"
  | "jobs"
  | "job"
  | "interview"
  | "report"
  | "compare"
  | "archive";

const TITLES: Record<Route, string> = {
  intro: "开场",
  home: "主页",
  upload: "上传 · 建立求职档案",
  resume: "简历 · 选择方式",
  "resume-qa": "简历 · 确认信息",
  "resume-draft": "简历 · 草稿",
  jobs: "岗位 · 搜索结果",
  job: "岗位 · 匹配详情",
  interview: "面试 · 进行中",
  report: "面试 · 报告",
  compare: "岗位 · 对比",
  archive: "匹配档案",
};

function readRoute(): Route {
  const raw = window.location.hash.replace(/^#\/?/, "");
  return (raw || "intro") as Route;
}

export default function App() {
  const [route, setRoute] = useState<Route>(readRoute);
  const [jobId, setJobId] = useState("j1");

  useEffect(() => {
    const onHash = () => setRoute(readRoute());
    window.addEventListener("hashchange", onHash);
    return () => window.removeEventListener("hashchange", onHash);
  }, []);

  const go = (next: Route) => {
    window.location.hash = "/" + next;
    setRoute(next);
  };

  return (
    <ProfileProvider>
      {route === "intro" ? (
        <Intro onEnter={() => go("home")} />
      ) : route === "home" ? (
        <Home go={go} />
      ) : route === "upload" ? (
        <Upload go={go} />
      ) : route === "resume" ? (
        <Resume go={go} />
      ) : route === "resume-qa" ? (
        <ResumeQA go={go} />
      ) : route === "resume-draft" ? (
        <ResumeDraft go={go} />
      ) : route === "jobs" ? (
        <Jobs
          go={go}
          onPick={(id) => {
            setJobId(id);
            go("job");
          }}
        />
      ) : route === "job" ? (
        <JobDetail go={go} jobId={jobId} />
      ) : route === "archive" ? (
        <Archive go={go} />
      ) : route === "interview" ? (
        <Interview go={go} jobId={jobId} />
      ) : route === "report" ? (
        <Report go={go} />
      ) : route === "compare" ? (
        <Compare go={go} />
      ) : (
        <Placeholder title={TITLES[route] ?? "页面"} onBack={() => go("home")} go={go} />
      )}
    </ProfileProvider>
  );
}
