import Link from "next/link";
import { Check, Circle, Play, ShieldCheck } from "@phosphor-icons/react";

export type LifecycleTask = {
  task_id: string;
  status: "draft" | "confirmed" | "rejected" | "completed";
  title?: string;
  updated_at?: string;
  source_diagnosis?: { source?: string };
  execution?: { status?: string; started_at?: string };
};

type LifecycleState = "loading" | "signed-out" | "empty" | "ready";

const stages = ["待审核", "已批准", "实验中", "已完成"];

function stageIndex(task: LifecycleTask) {
  if (task.status === "completed") return 3;
  if (task.execution?.status === "in_progress") return 2;
  if (task.status === "confirmed") return 1;
  return 0;
}

function sourceLabel(task: LifecycleTask) {
  return task.source_diagnosis?.source === "consented_reactivation_aggregate" ? "匿名再激活试点" : "Shopify 店铺级汇总";
}

export function OpportunityLifecycle({ tasks, state }: { tasks: LifecycleTask[]; state: LifecycleState }) {
  const activeTasks = tasks.filter((task) => ["shopify_aggregate", "consented_reactivation_aggregate"].includes(task.source_diagnosis?.source ?? ""));

  return <section className="lifecycle-board" aria-labelledby="lifecycle-title">
    <header className="lifecycle-head">
      <div><p className="eyebrow">Opportunity lifecycle</p><h2 id="lifecycle-title">真实机会生命周期</h2><p>每一步都需要人工确认；系统不调用外部渠道，也不保存客户联系方式。</p></div>
      <span className="lifecycle-count">{activeTasks.length.toString().padStart(2, "0")} ACTIVE RECORDS</span>
    </header>
    {state === "loading" && <div className="lifecycle-empty">正在读取当前账号的真实任务…</div>}
    {state === "signed-out" && <div className="lifecycle-empty"><strong>登录后查看真实生命周期</strong><span>当前未读取任何商家任务。</span><Link className="button button-ghost" href="/data">前往登录</Link></div>}
    {state !== "loading" && state !== "signed-out" && !activeTasks.length && <div className="lifecycle-empty"><strong>尚无真实机会记录</strong><span>满足数据门槛后创建审核草案，生命周期会从这里开始。</span></div>}
    {activeTasks.length > 0 && <div className="lifecycle-list">{activeTasks.map((task) => {
      const current = stageIndex(task);
      const actionHref = current === 3 ? "/learning" : current > 0 ? "/campaigns" : "/opportunities";
      const actionLabel = current === 3 ? "查看结果" : current === 2 ? "回传结果" : current === 1 ? "进入执行工作台" : "继续审核";
      return <article className="lifecycle-item" key={task.task_id}>
        <div className="lifecycle-summary"><span>{sourceLabel(task)}</span><h3>{task.title ?? "未命名真实机会"}</h3><small>更新于 {formatTime(task.updated_at)} · ID {task.task_id}</small></div>
        <ol className="lifecycle-steps" aria-label={`${task.title ?? "机会"} 当前阶段：${stages[current]}`}>{stages.map((label, index) => <li className={index < current ? "done" : index === current ? "current" : ""} key={label}>{index < current ? <Check size={13} weight="bold" /> : index === current && index === 2 ? <Play size={13} weight="fill" /> : index === current ? <ShieldCheck size={13} weight="fill" /> : <Circle size={10} />}<span>{label}</span></li>)}</ol>
        <Link className="button button-ghost" href={actionHref}>{actionLabel}</Link>
      </article>;
    })}</div>}
  </section>;
}

function formatTime(value?: string) {
  if (!value) return "时间未知";
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? "时间未知" : date.toLocaleString("zh-CN", { month: "2-digit", day: "2-digit", hour: "2-digit", minute: "2-digit" });
}
