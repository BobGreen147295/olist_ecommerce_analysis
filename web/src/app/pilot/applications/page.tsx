"use client";

import { useEffect, useState } from "react";
import Link from "next/link";

const API_BASE_URL = process.env.NEXT_PUBLIC_REVENUEOPS_API_URL?.replace(/\/$/, "");
const CHALLENGES: Record<string, string> = { repeat_purchase: "复购表现", refunds: "退款变化", discounts: "折扣效率", other: "其他收入问题" };
type Application = { application_id: string; contact_email: string; shop_domain: string; monthly_orders: string; challenge: string; status: string; created_at: string };

export default function PilotApplicationsPage() {
  const [applications, setApplications] = useState<Application[]>([]);
  const [message, setMessage] = useState("正在读取申请…");

  useEffect(() => {
    const token = sessionStorage.getItem("revenueops_access_token");
    if (!API_BASE_URL || !token) { setMessage("请先在数据连接页使用管理员账号登录。"); return; }
    fetch(`${API_BASE_URL}/v1/pilot-applications`, { headers: { Authorization: `Bearer ${token}` } })
      .then(async (response) => {
        const data = await response.json().catch(() => ({}));
        if (!response.ok) throw new Error(data.error ?? "无法读取申请");
        setApplications(data.applications ?? []);
        setMessage(data.applications?.length ? "" : "目前还没有试点申请。");
      })
      .catch((error) => setMessage(error instanceof Error ? error.message : "无法读取申请"));
  }, []);

  return <main className="page-content">
    <section className="section-heading"><div><p className="eyebrow">PILOT OPERATIONS</p><h1>试点申请</h1></div><Link className="button button-ghost" href="/pilot">查看公开页面</Link></section>
    {message && <section className="card"><p>{message}</p>{message.includes("登录") && <Link className="button button-primary" href="/data">前往登录</Link>}</section>}
    {applications.length > 0 && <section className="card pilot-applications-table"><table><thead><tr><th>提交时间</th><th>店铺</th><th>联系邮箱</th><th>订单量</th><th>问题</th></tr></thead><tbody>{applications.map((item) => <tr key={item.application_id}><td>{new Date(item.created_at).toLocaleString("zh-CN")}</td><td>{item.shop_domain}</td><td>{item.contact_email}</td><td>{item.monthly_orders}</td><td>{CHALLENGES[item.challenge] ?? item.challenge}</td></tr>)}</tbody></table></section>}
  </main>;
}
