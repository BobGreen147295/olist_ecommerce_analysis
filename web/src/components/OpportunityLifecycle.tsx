import Link from "next/link";
import { Check, Circle, Play, ShieldCheck } from "@phosphor-icons/react";
import { useI18n } from "./I18n";

export type LifecycleTask = {
  task_id: string;
  status: "draft" | "confirmed" | "rejected" | "completed";
  title?: string;
  updated_at?: string;
  source_diagnosis?: { source?: string };
  execution?: { status?: string; started_at?: string };
};

type LifecycleState = "loading" | "signed-out" | "empty" | "ready";

function stageIndex(task: LifecycleTask) {
  if (task.status === "completed") return 3;
  if (task.execution?.status === "in_progress") return 2;
  if (task.status === "confirmed") return 1;
  return 0;
}

export function OpportunityLifecycle({ tasks, state }: { tasks: LifecycleTask[]; state: LifecycleState }) {
  const { locale } = useI18n();
  const english = locale === "en";
  const stages = english ? ["Review", "Approved", "Running", "Completed"] : ["待审核", "已批准", "实验中", "已完成"];
  const tx = (zh: string, en: string) => english ? en : zh;
  const sourceLabel = (task: LifecycleTask) => task.source_diagnosis?.source === "consented_reactivation_aggregate" ? tx("匿名再激活试点", "Anonymous reactivation pilot") : tx("Shopify 店铺级汇总", "Shopify store aggregate");
  const activeTasks = tasks.filter((task) => ["shopify_aggregate", "consented_reactivation_aggregate"].includes(task.source_diagnosis?.source ?? ""));

  return <section className="lifecycle-board" aria-labelledby="lifecycle-title">
    <header className="lifecycle-head">
      <div><p className="eyebrow">Opportunity lifecycle</p><h2 id="lifecycle-title">{tx("真实机会生命周期", "Real opportunity lifecycle")}</h2><p>{tx("每一步都需要人工确认；系统不调用外部渠道，也不保存客户联系方式。", "Every step requires human approval. The system does not call external channels or store customer contact details.")}</p></div>
      <span className="lifecycle-count">{activeTasks.length.toString().padStart(2, "0")} {english ? "ACTIVE RECORDS" : "条活跃记录"}</span>
    </header>
    {state === "loading" && <div className="lifecycle-empty">{tx("正在读取当前账号的真实任务…", "Loading real tasks for this account…")}</div>}
    {state === "signed-out" && <div className="lifecycle-empty"><strong>{tx("登录后查看真实生命周期", "Sign in to view the real lifecycle")}</strong><span>{tx("当前未读取任何商家任务。", "No merchant tasks are being read.")}</span><Link className="button button-ghost" href="/data">{tx("前往登录", "Go to sign in")}</Link></div>}
    {state !== "loading" && state !== "signed-out" && !activeTasks.length && <div className="lifecycle-empty"><strong>{tx("尚无真实机会记录", "No real opportunity records yet")}</strong><span>{tx("满足数据门槛后创建审核草案，生命周期会从这里开始。", "Create a review draft after the data threshold is met; its lifecycle will start here.")}</span></div>}
    {activeTasks.length > 0 && <div className="lifecycle-list">{activeTasks.map((task) => {
      const current = stageIndex(task);
      const actionHref = current === 3 ? "/learning" : current > 0 ? "/campaigns" : "/opportunities";
      const actionLabel = current === 3 ? tx("查看结果", "View results") : current === 2 ? tx("回传结果", "Submit results") : current === 1 ? tx("进入执行工作台", "Open execution workspace") : tx("继续审核", "Continue review");
      return <article className="lifecycle-item" key={task.task_id}>
        <div className="lifecycle-summary"><span>{sourceLabel(task)}</span><h3>{task.title ?? tx("未命名真实机会", "Untitled real opportunity")}</h3><small>{tx("更新于", "Updated")} {formatTime(task.updated_at, locale)} · ID {task.task_id}</small></div>
        <ol className="lifecycle-steps" aria-label={`${task.title ?? tx("机会", "Opportunity")} ${tx("当前阶段", "current stage")}: ${stages[current]}`}>{stages.map((label, index) => <li className={index < current ? "done" : index === current ? "current" : ""} key={label}>{index < current ? <Check size={13} weight="bold" /> : index === current && index === 2 ? <Play size={13} weight="fill" /> : index === current ? <ShieldCheck size={13} weight="fill" /> : <Circle size={10} />}<span>{label}</span></li>)}</ol>
        <Link className="button button-ghost" href={actionHref}>{actionLabel}</Link>
      </article>;
    })}</div>}
  </section>;
}

function formatTime(value: string | undefined, locale: "zh-CN" | "en") {
  if (!value) return locale === "en" ? "Unknown time" : "时间未知";
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? (locale === "en" ? "Unknown time" : "时间未知") : date.toLocaleString(locale === "en" ? "en-US" : "zh-CN", { month: "2-digit", day: "2-digit", hour: "2-digit", minute: "2-digit" });
}
