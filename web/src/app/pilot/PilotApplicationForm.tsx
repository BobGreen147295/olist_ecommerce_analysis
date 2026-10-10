"use client";

import { FormEvent, useState } from "react";
import Link from "next/link";

const API_BASE_URL = process.env.NEXT_PUBLIC_REVENUEOPS_API_URL?.replace(/\/$/, "");
const CONTACT_EMAIL = process.env.NEXT_PUBLIC_REVENUEOPS_CONTACT_EMAIL?.trim() || "duan.hongbo@outlook.com";

export function PilotApplicationForm() {
  const [status, setStatus] = useState("");
  const [busy, setBusy] = useState(false);

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const formElement = event.currentTarget;
    if (busy) return;
    if (!API_BASE_URL) { setStatus(CONTACT_EMAIL ? "在线申请暂不可用，请使用旁边的备用邮箱联系。" : "在线申请暂不可用，请稍后重试。"); return; }
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
    } catch {
      setStatus(CONTACT_EMAIL ? "申请未确认收到，请重试或使用旁边的备用邮箱联系。表单内容已保留。" : "申请未确认收到，请稍后重试。表单内容已保留。");
    } finally {
      setBusy(false);
    }
  }

  return <section className="card pilot-application" id="apply">
    <div><p className="eyebrow">申请免费试点</p><h2>先确认是否适合，不上传订单</h2><p>这里只收合作联系信息。通过初筛后，我们才会与你确认授权范围。</p>
      {CONTACT_EMAIL && <aside className="pilot-backup-contact" aria-label="备用联系邮箱"><h3>也可以直接邮件联系</h3><p>表单无法提交，或想先问清楚？</p><a href={`mailto:${CONTACT_EMAIL}?subject=${encodeURIComponent("RevenueOps 试点咨询")}`}>{CONTACT_EMAIL}</a><p>请只提供店铺网址和想核对的问题，不要发送订单、客户资料或访问令牌。点击将打开你的邮件应用，不会自动发送。</p></aside>}
    </div>
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
