import Top from "../components/Top";
import Band from "../components/Band";
import { useProfile } from "../store";
import { JOBS, matchOf } from "../jobs";
import type { Route } from "../App";

type Props = {
  go: (r: Route) => void;
};

export default function Compare({ go }: Props) {
  const { profile, compare, toggleCompare } = useProfile();

  const picked = compare
    .map((id) => JOBS.find((j) => j.id === id))
    .filter((j): j is NonNullable<typeof j> => !!j)
    .map((job) => ({ job, m: matchOf(job, profile) }))
    .sort((a, b) => b.m.score - a.m.score);

  return (
    <div className="shell" id="main">
      <Top
        onHome={() => go("home")}
        back={{ label: "返回结果列表", onClick: () => go("jobs") }}
      />

      <main className="page">
        <div className="eyebrow">B 区 · 岗位对比</div>
        <h1 className="h1 mt-16">岗位对比</h1>
        <p className="lead">
          {picked.length ? `并排比较 ${picked.length} 个岗位，最多 4 个。` : "还没有选岗位。"}
        </p>

        {picked.length === 0 ? (
          <div className="panel mt-32">
            <div className="eyebrow">对比 · 0 / 4</div>
            <p className="lead">
              去岗位详情里点「加入对比」，选满 2 个就能在这里并排看。
            </p>
            <button className="pill solid mt-24" onClick={() => go("jobs")} type="button">
              去看岗位
            </button>
          </div>
        ) : (
          <>
            <div
              className="row wrap mt-32"
              style={{ gap: 16, alignItems: "stretch" }}
            >
              {picked.map(({ job, m }, i) => (
                <div
                  key={job.id}
                  style={{
                    flex: "1 1 260px",
                    minWidth: 0,
                    display: "flex",
                    flexDirection: "column",
                  }}
                >
                  <div
                    className={i === 0 ? "panel y" : "panel"}
                    style={{ padding: "18px 18px 16px" }}
                  >
                    <div className="row between" style={{ gap: 8, alignItems: "flex-start" }}>
                      {i === 0 ? (
                        <span className="tag">推荐</span>
                      ) : (
                        <span className="eyebrow">{String(i + 1).padStart(2, "0")}</span>
                      )}
                      <button
                        className="pill sm"
                        onClick={() => {
                          toggleCompare(job.id);
                        }}
                        type="button"
                      >
                        移除
                      </button>
                    </div>
                    <div className="h2 mt-16">{job.company}</div>
                    <div className="small">{job.title}</div>
                  </div>

                  <div
                    style={{
                      flex: "1 1 auto",
                      borderLeft: "1.5px solid var(--ink)",
                      borderRight: "1.5px solid var(--ink)",
                      borderBottom: "1.5px solid var(--ink)",
                    }}
                  >
                    <div style={{ padding: "13px 18px", minHeight: 76 }}>
                      <div className="eyebrow">匹配分</div>
                      <div className="num mt-8" style={{ fontSize: 32, lineHeight: 1 }}>
                        {m.score}
                      </div>
                    </div>

                    <div
                      style={{
                        padding: "13px 18px",
                        minHeight: 76,
                        borderTop: "1px solid var(--line)",
                      }}
                    >
                      <div className="eyebrow">薪资</div>
                      <div className="mt-8">{job.salary}</div>
                    </div>

                    <div
                      style={{
                        padding: "13px 18px",
                        minHeight: 76,
                        borderTop: "1px solid var(--line)",
                      }}
                    >
                      <div className="eyebrow">城市</div>
                      <div className="mt-8">{job.city}</div>
                    </div>

                    <div
                      style={{
                        padding: "13px 18px",
                        minHeight: 76,
                        borderTop: "1px solid var(--line)",
                      }}
                    >
                      <div className="eyebrow">类型</div>
                      <div className="mt-8">{job.employment}</div>
                    </div>

                    <div
                      style={{
                        padding: "13px 18px",
                        minHeight: 76,
                        borderTop: "1px solid var(--line)",
                      }}
                    >
                      <div className="eyebrow">核验</div>
                      <div className="row mt-8" style={{ gap: 8 }}>
                        <i
                          className={
                            job.verify === "ok"
                              ? "dot"
                              : job.verify === "dead"
                                ? "dot dead"
                                : "dot hollow"
                          }
                        />
                        <span className="fs-13">
                          {job.verify === "ok"
                            ? "已核验"
                            : job.verify === "dead"
                              ? "来源失效"
                              : "待核验"}
                        </span>
                      </div>
                    </div>

                    <div
                      style={{
                        padding: "13px 18px",
                        minHeight: 76,
                        borderTop: "1px solid var(--line)",
                      }}
                    >
                      <div className="eyebrow">缺口</div>
                      <div className="mt-8">
                        {m.gap.length + m.fail.length === 0
                          ? "无"
                          : `${m.gap.length + m.fail.length} 项`}
                      </div>
                    </div>

                    <div
                      style={{
                        padding: "13px 18px",
                        minHeight: 76,
                        borderTop: "1px solid var(--line)",
                      }}
                    >
                      <div className="eyebrow">下一步</div>
                      <button
                        className="pill sm mt-8"
                        onClick={() => go("interview")}
                        type="button"
                      >
                        面这个
                      </button>
                    </div>
                  </div>
                </div>
              ))}
            </div>

            {picked.length >= 2 && (
              <p className="small mt-24">
                推荐顺序：{picked.map((p) => p.job.company).join(" > ")}。
                {picked[0].job.company} 的匹配最高且硬性条件全部满足；
                后面的岗位各有缺口，需要先补证据。
              </p>
            )}
          </>
        )}
      </main>

      <Band
        step={2}
        total={4}
        label={`岗位对比 · ${picked.length} / 4 个`}
        action={
          picked.length
            ? { label: "继续挑岗位", onClick: () => go("jobs") }
            : undefined
        }
      />
    </div>
  );
}
