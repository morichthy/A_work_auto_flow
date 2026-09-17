import { useEffect, useState, useRef } from "react";
import { api, type Job, type Capabilities } from "./api";
import { Relations } from "./Relations";
import { Evidence } from "./Evidence";
import { Memory } from "./Memory";
import { MaterialQuery } from "./MaterialQuery";
import { WorkspaceSettings } from "./WorkspaceSettings";
import { RetainedPanel } from "./RetainedPanel";

import { MaterialNavigation } from "./MaterialNavigation";
import { CurrentReadingProvider, CurrentReadingNote } from "./CurrentReading";
type Status = {
  root: string;
  synthetic: boolean;
  monitor_running: boolean;
  interval_seconds: number;
  error: string | null;
  result: unknown;
  modules: { path: string; title: string; exists: boolean }[];
  capabilities: Record<string, { status: string }> | null;
};
// 功能注册是编译时确定的导航；添加页面不需要动态执行第三方插件。
export const pages = [
  { id: "home", title: "工作台", icon: "◫" },
  { id: "materials", title: "材料查询", icon: "▦" },
  { id: "relations", title: "材料关系", icon: "◇" },
  { id: "evidence", title: "证据与影响", icon: "▤" },
  { id: "memory", title: "系统记忆", icon: "▥" },
  { id: "tasks", title: "任务与监测", icon: "◷" },
  { id: "settings", title: "工作区设置", icon: "⚙" },
];
export default function App() {
  return (
    <CurrentReadingProvider>
      <Workbench />
    </CurrentReadingProvider>
  );
}
function Workbench() {
  const [page, setPage] = useState(
    location.hash.replace(/^#\/?/, "").split("?")[0] || "home",
  );
  const [status, setStatus] = useState<Status | null>(null);
  const [caps, setCaps] = useState<Capabilities | null>(null);
  const [jobs, setJobs] = useState<Job[]>([]);
  const [message, setMessage] = useState("");
  const [revision, setRevision] = useState(0);
  const signature = useRef<string | null>(null);
  async function refresh() {
    try {
      const [s, j, c] = await Promise.all([
        api<Status>("workbench", undefined, true),
        api<{ jobs: Job[] }>("jobs"),
        api<Capabilities>("capabilities"),
      ]);
      if (c.api_version !== 1)
        throw Error("API 版本不兼容，请刷新或升级工作台。");
      setStatus(s);
      setJobs(j.jobs);
      setCaps(c);
      // 完成的材料相关任务使视图失效，初始清单和进度不触发重载。
      const next = j.jobs
        .filter(
          (x) =>
            x.status === "succeeded" &&
            ["refresh", "monitor", "keywords", "semantic"].includes(x.kind),
        )
        .map((x) => x.id)
        .join();
      if (signature.current !== next) {
        if (signature.current !== null) setRevision((r) => r + 1);
        signature.current = next;
      }
      const stale = j.jobs.find(
        (x) =>
          ["freshness", "refresh"].includes(x.kind) && x.status === "succeeded",
      );
      if (stale && (stale.result as { stale?: boolean })?.stale)
        setMessage("材料版本与当前视图不同，请刷新投影；候选需重新核对。");
    } catch (e) {
      setMessage(String(e));
    }
  }
  useEffect(() => {
    const change = () =>
      setPage(location.hash.replace(/^#\/?/, "").split("?")[0] || "home");
    window.addEventListener("hashchange", change);
    refresh();
    const timer = setInterval(refresh, 5000);
    return () => {
      clearInterval(timer);
      window.removeEventListener("hashchange", change);
    };
  }, []);
  async function launch(kind: string, seeds?: string[], excluded?: string[]) {
    try {
      await api("jobs", { kind, ...(seeds ? { seeds, excluded } : {}) });
      setMessage("任务已排队，可在任务与监测中查看进度。");
      await refresh();
    } catch (e) {
      setMessage(String(e));
    }
  }
  const actions = (
    <div className="row">
      <button onClick={() => launch("monitor")}>立即检查一次</button>
      <button
        onClick={() =>
          api("action", { action: "start-monitor" }, true)
            .then(refresh)
            .catch((e) => setMessage(e.message))
        }
      >
        开启持续监测
      </button>
      <button
        onClick={() =>
          api("action", { action: "stop-monitor" }, true)
            .then(refresh)
            .catch((e) => setMessage(e.message))
        }
      >
        停止持续监测
      </button>
      <button onClick={() => launch("doctor")}>检查环境能力</button>
    </div>
  );
  const taskList = (
    <section className="card">
      <h2>后台任务</h2>
      {jobs.length ? (
        jobs.map((j) => (
          <article className="proposal" key={j.id}>
            <div className="row spread">
              <strong>
                {(
                  {
                    refresh: "材料投影",
                    freshness: "版本核对",
                    keywords: "关键词候选",
                    semantic: "语义候选",
                    monitor: "只读监测",
                    doctor: "环境检查",
                  } as Record<string, string>
                )[j.kind] || j.kind}
              </strong>
              <span className="badge">{j.status}</span>
            </div>
            {/* Success is authoritative for completion. Progress callbacks are
                optional and their zero counters must not imply pending work. */}
            <progress
              max={j.status === "succeeded" ? 1 : j.total || 1}
              value={
                j.status === "succeeded" ? 1 : j.total > 0 ? j.done : undefined
              }
            />
            <span className="muted">
              {" "}
              {j.status === "succeeded"
                ? "已完成"
                : j.total > 0
                  ? `${j.done} / ${j.total}`
                  : ["queued", "running"].includes(j.status)
                    ? "正在确定处理数量"
                    : "未提供分项计数"}
            </span>
            {["queued", "running"].includes(j.status) && (
              <button onClick={() => api("cancel", { id: j.id }).then(refresh)}>
                取消
              </button>
            )}
            {j.error && <p className="risk">{j.error}</p>}
            <details>
              <summary>结果与覆盖范围</summary>
              <pre>{JSON.stringify(j.result, null, 2)}</pre>
            </details>
          </article>
        ))
      ) : (
        <p className="muted">尚无分析任务。任务不会自动重试或在开机时启动。</p>
      )}
    </section>
  );
  return (
    <div className="app">
      <aside className="sidebar">
        <a className="brand" href="#/home">
          <span className="brand-icon">研</span>
          <div>
            研发工作台<small>材料 · 证据 · 联系</small>
          </div>
        </a>
        <nav>
          {pages.map((p) => (
            <a
              key={p.id}
              href={"#/" + p.id}
              className={page === p.id ? "active" : ""}
            >
              <span>{p.icon}</span>
              {p.title}
            </a>
          ))}
        </nav>
        <div className="sidebar-foot">
          本机工作区
          <br />
          <span>原始记录可追溯</span>
        </div>
      </aside>
      <div className="content">
        <header className="topbar">
          <span>AI 研发工作区</span>
          <details className="environment-menu">
            <summary>观察与环境</summary>
            {actions}
            <a href="#/tasks">查看任务与监测</a>
          </details>
          <span>
            {status?.monitor_running ? "● 只读监测运行中" : "○ 按需分析"}
          </span>
        </header>
        <div className="page">
          {status?.synthetic && (
            <div className="demo">
              合成测试沙盒 · 全部样例为虚构，不属于正式业务证据
            </div>
          )}
          {message && (
            <div className="alert" role="status">
              <span>{message}</span>
              <button aria-label="关闭提示" onClick={() => setMessage("")}>
                ×
              </button>
            </div>
          )}
          {/* 常驻组件保留跨导航草稿；仅首次打开设置页时读取服务器。 */}
          <WorkspaceSettings active={page === "settings"} />
          <RetainedPanel active={page === "materials"}>
            <MaterialQuery />
          </RetainedPanel>
          <RetainedPanel active={page === "memory"}>
            <Memory />
          </RetainedPanel>
          <RetainedPanel active={page === "relations"}>
            <Relations revision={revision} error={setMessage} launch={launch} />
          </RetainedPanel>
          <RetainedPanel active={page === "evidence"}>
            <Evidence revision={revision} error={setMessage} />
          </RetainedPanel>
          {!["home", "tasks"].includes(page) ? null : page === "tasks" ? (
            <>
              <div className="page-heading">
                <div>
                  <p className="eyebrow">执行状态 / 本机记录</p>
                  <h1>任务与只读监测</h1>
                </div>
              </div>
              <section className="card">
                {actions}
                <p>
                  持续监测每 {status?.interval_seconds || 60}{" "}
                  秒检查一次。关闭标签页不会停止服务；Ctrl+C 结束工作台。
                </p>
                {status?.error && <p className="risk">{status.error}</p>}
                <details>
                  <summary>最近监测结果</summary>
                  <pre>{JSON.stringify(status?.result, null, 2)}</pre>
                </details>
              </section>
              {taskList}
            </>
          ) : (
            <>
              <div className="page-heading">
                <div>
                  <p className="eyebrow">本地研发 / 工作区总览</p>
                  <h1>把材料连接到问题</h1>
                  <p className="muted">
                    整理来源，查看依据，发现值得进一步研究的联系。
                  </p>
                </div>
              </div>
              <CurrentReadingNote />
              <MaterialNavigation />
              <p className="id workspace-path">{status?.root}</p>
              <p className="muted">
                日常入口：rdwork · 安装升级：setup.cmd ·{" "}
                {caps?.graph_ready ? "已有材料视图" : "尚未建立材料视图"}
              </p>
            </>
          )}
        </div>
      </div>
    </div>
  );
}
