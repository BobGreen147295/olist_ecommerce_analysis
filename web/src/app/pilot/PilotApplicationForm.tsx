"use client";

import { FormEvent, useState } from "react";
import Link from "next/link";

const API_BASE_URL = process.env.NEXT_PUBLIC_REVENUEOPS_API_URL?.replace(/\/$/, "");

export function PilotApplicationForm() {
  const [status, setStatus] = useState("");
  const [busy, setBusy] = useState(false);

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const formElement = event.currentTarget;
    if (!API_BASE_URL) { setStatus("申请服务尚未配置，请稍后重试。"); return; }
    const form = new FormData(formElement);
    setBusy(true); setStatus("");
    try {
      const response = await fetch(`${API_BASE_URL}/v1/pilot-applications`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(Object.fromEntries(form.entries())),
      });
      const data = await response.json().catch(() => ({}));
      if (!response.ok) throw new Error(data.error ?? "提交失败，请稍后重试。");
      formElement.reset();
      setStatus("申请已收到。我们会在 2 个工作日内通过邮箱联系你确认范围。");
    } catch (error) {
      setStatus(error instanceof Error ? error.message : "提交失败，请稍后重试。");
    } finally {
      setBusy(false);
    }
  }

  return <section className="card pilot-application" id="apply">
    <div><p className="eyebrow">申请免费试点</p><h2>先确认是否适合，不上传订单</h2><p>这里只收合作联系信息。通过初筛后，我们才会与你确认授权范围。</p></div>
    <form onSubmit={submit}>
      <label>联系邮箱<input required type="email" name="contact_email" autoComplete="email" placeholder="you@company.com" /></label>
      <label>Shopify 店铺域名<input required name="shop_domain" inputMode="url" placeholder="your-store.myshopify.com" /></label>
      <label>近 30 天订单量<select required name="monthly_orders" defaultValue=""><option value="" disabled>请选择</option><option value="1-49">1–49 单</option><option value="50-199">50–199 单</option><option value="200-999">200–999 单</option><option value="1000+">1,000 单以上</option></select></label>
      <label>最想解决的问题<select required name="challenge" defaultValue=""><option value="" disabled>请选择</option><option value="repeat_purchase">复购表现</option><option value="refunds">退款变化</option><option value="discounts">折扣效率</option><option value="other">其他收入问题</option></select></label>
      <label className="pilot-honeypot" aria-hidden="true">网站<input name="website" tabIndex={-1} autoComplete="off" /></label>
      <label className="pilot-consent"><input required type="checkbox" name="terms_accepted" value="true" /> 我同意 RevenueOps 保存以上联系信息用于试点沟通，并已阅读 <Link href="/privacy" target="_blank">数据处理条款</Link>。</label>
      <button className="button button-primary" type="submit" disabled={busy}>{busy ? "正在提交…" : "申请免费试点"}</button>
      {status && <p className="pilot-form-status" role="status">{status}</p>}
    </form>
  </section>;
}
