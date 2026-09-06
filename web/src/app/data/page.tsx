"use client";

import { useEffect, useState } from "react";
import { PageHeading, StatusBadge } from "@/components/Ui";

const sources = [["订单与客户历史","已接入","Olist 历史样本","仅用于产品验证"],["活动执行回执","未接入","Klaviyo / Braze","接入后才可判断真实触达"],["广告消耗与转化","未接入","Meta / Google Ads","接入后才可计算渠道 ROI"],["履约与退款成本","未接入","Shopify / ERP","接入后才可计算净利润"]];

const connectors = [
  { name: "Shopify", type: "订单、客户、产品、退款", detail: "优先接入 · 形成收入与复购基线", icon: "S", frequency: "每日同步", access: "只读", fields: "订单金额、币种、产品、客户标识、退款状态", purpose: "建立收入、复购和退款基线" },
  { name: "Klaviyo", type: "邮件事件、订阅、触达回执", detail: "第二阶段 · 验证活动是否真的生效", icon: "K", frequency: "每 6 小时", access: "只读", fields: "发送、送达、打开、点击、转化事件", purpose: "验证运营活动的真实触达与增量" },
  { name: "Meta Ads", type: "广告消耗、投放、转化", detail: "第三阶段 · 计算渠道级增量 ROI", icon: "M", frequency: "每日同步", access: "只读", fields: "账户、广告组、消耗、点击、转化", purpose: "建立渠道成本与收入归因" },
];
const API_BASE_URL = process.env.NEXT_PUBLIC_REVENUEOPS_API_URL?.replace(/\/$/, "");
const SHOPIFY_SUMMARY_CACHE_KEY = "revenueops_shopify_summary_v1";
type ShopifyReadiness = { state: "configuration_required" | "ready_to_authorize"; message: string; required_scopes: string[] };
type ShopifyDeltas = { orders: number; customers: number; products: number; inventory_items: number };
type ShopifyConnection = { provider: "shopify"; shop_domain: string; status: "connected" | "synced"; last_synced_at: string | null; summary: { orders: number; customers: number; products: number; inventory_items: number; currency_code: string | null; is_development_store?: boolean } | null; comparison?: { previous_synced_at: string; deltas: ShopifyDeltas } | null };
type CsvPreview = { columns: string[]; row_count: number };

function parseCsv(text: string) {
  const rows: string[][] = [[]]; let value = ""; let quoted = false;
  for (let index = 0; index < text.length; index += 1) {
    const char = text[index];
    if (char === '"' && quoted && text[index + 1] === '"') { value += char; index += 1; }
    else if (char === '"') quoted = !quoted;
    else if (char === "," && !quoted) { rows.at(-1)?.push(value); value = ""; }
    else if ((char === "\n" || char === "\r") && !quoted) { if (char === "\r" && text[index + 1] === "\n") index += 1; rows.at(-1)?.push(value); rows.push([]); value = ""; }
    else value += char;
  }
  if (value || rows.at(-1)?.length) rows.at(-1)?.push(value);
  return rows.filter((row) => row.some((cell) => cell.trim()));
}
function csvCell(value: string) { return `"${value.replaceAll('"', '""')}"`; }
async function sanitizeShopifyOrders(file: File) {
  const rows = parseCsv(await file.text()); const headers = rows.shift()?.map((header) => header.trim()) ?? [];
  const find = (name: string) => headers.findIndex((header) => header.toLowerCase() === name.toLowerCase());
  const order = find("Name"), date = find("Created at"), total = find("Total"), currency = find("Currency"), consent = find("Accepts Marketing"), email = find("Email");
  if ([order, date, total, currency, consent, email].some((index) => index < 0)) throw new Error("请选择 Shopify 的订单导出 CSV；需包含 Name、Created at、Total、Currency、Accepts Marketing、Email 列。");
  const saltKey = "revenueops_local_csv_salt_v1"; let salt = localStorage.getItem(saltKey);
  if (!salt) { salt = crypto.randomUUID(); localStorage.setItem(saltKey, salt); }
  const digest = async (emailValue: string) => Array.from(new Uint8Array(await crypto.subtle.digest("SHA-256", new TextEncoder().encode(`${salt}\0${emailValue.trim().toLowerCase()}`)))).map((byte) => byte.toString(16).padStart(2, "0")).join("");
  const cleanRows = await Promise.all(rows.map(async (row) => [row[order] ?? "", row[date] ?? "", row[total] ?? "", row[currency] ?? "", row[consent] ?? "", row[email]?.trim() ? await digest(row[email]) : ""]));
  const content = [["order_id", "ordered_at", "total_amount", "currency", "marketing_consent", "customer_id"], ...cleanRows].map((row) => row.map(csvCell).join(",")).join("\n");
  return new File([content], `revenueops-safe-${file.name}`, { type: "text/csv" });
}

export default function DataPage() {
  const [shopifyReadiness, setShopifyReadiness] = useState<ShopifyReadiness | null>(null);
  const [selected, setSelected] = useState<typeof connectors[number] | null>(null);
  const [accessToken, setAccessToken] = useState("");
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [shopDomain, setShopDomain] = useState("");
  const [registrationCode, setRegistrationCode] = useState("");
  const [isRegistering, setIsRegistering] = useState(false);
  const [connectionError, setConnectionError] = useState("");
  const [shopifyConnection, setShopifyConnection] = useState<ShopifyConnection | null>(null);
  const [isSyncing, setIsSyncing] = useState(false);
  const [csvFile, setCsvFile] = useState<File | null>(null);
  const [csvPreview, setCsvPreview] = useState<CsvPreview | null>(null);
  const [csvMapping, setCsvMapping] = useState<Record<string, string>>({});
  const [csvMessage, setCsvMessage] = useState("");
  const [isCsvBusy, setIsCsvBusy] = useState(false);
  function rememberShopifyConnection(connection: ShopifyConnection | null) {
    setShopifyConnection(connection);
    if (connection?.summary) localStorage.setItem(SHOPIFY_SUMMARY_CACHE_KEY, JSON.stringify({ connection, cached_at: Date.now() }));
  }
  async function loadShopifyConnection(token: string) {
    if (!API_BASE_URL || !token) return;
    const response = await fetch(`${API_BASE_URL}/v1/integrations/shopify/status`, { headers: { Authorization: `Bearer ${token}` } });
    if (response.status === 401) {
      sessionStorage.removeItem("revenueops_access_token");
      setAccessToken("");
      setShopifyConnection(null);
      setConnectionError("登录已过期，请重新登录后继续管理 Shopify 连接。");
      return;
    }
    const data = await response.json().catch(() => ({}));
    if (response.ok) rememberShopifyConnection(data.connection ?? null);
  }
  useEffect(() => {
    const cached = JSON.parse(localStorage.getItem(SHOPIFY_SUMMARY_CACHE_KEY) ?? "null");
    if (cached?.connection?.summary && Date.now() - cached.cached_at < 86_400_000) setShopifyConnection(cached.connection);
    const token = sessionStorage.getItem("revenueops_access_token") ?? "";
    setAccessToken(token);
    if (!API_BASE_URL) return;
    fetch(`${API_BASE_URL}/v1/integrations/shopify/readiness`).then((response) => response.ok ? response.json() : null).then(setShopifyReadiness).catch(() => setShopifyReadiness(null));
    loadShopifyConnection(token);
    if (new URLSearchParams(window.location.search).get("shopify") === "connected") setSelected(connectors[0]);
  }, []);
  async function loginForConnection() {
    setConnectionError("");
    const response = await fetch(`${API_BASE_URL}/v1/auth/login`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ username, password }) });
    const data = await response.json().catch(() => ({}));
    if (!response.ok || !data.access_token) { setConnectionError(data.error ?? "登录失败，请稍后重试。"); return; }
    sessionStorage.setItem("revenueops_access_token", data.access_token);
    setAccessToken(data.access_token); setPassword(""); loadShopifyConnection(data.access_token);
  }
  async function registerForConnection() {
    setConnectionError("");
    const response = await fetch(`${API_BASE_URL}/v1/auth/register`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ username, password, registration_code: registrationCode }) });
    const data = await response.json().catch(() => ({}));
    if (!response.ok || !data.access_token) { setConnectionError(data.error ?? "创建账号失败，请稍后重试。"); return; }
    sessionStorage.setItem("revenueops_access_token", data.access_token);
    setAccessToken(data.access_token); setPassword(""); setRegistrationCode(""); loadShopifyConnection(data.access_token);
  }
  async function beginShopifyAuthorization() {
    setConnectionError("");
    const response = await fetch(`${API_BASE_URL}/v1/integrations/shopify/authorize`, { method: "POST", headers: { "Content-Type": "application/json", Authorization: `Bearer ${accessToken}` }, body: JSON.stringify({ shop_domain: shopDomain }) });
    if (response.status === 401) { sessionStorage.removeItem("revenueops_access_token"); setAccessToken(""); setConnectionError("登录已过期，请重新登录。"); return; }
    const data = await response.json().catch(() => ({}));
    if (!response.ok || !data.authorization_url) { setConnectionError(data.error ?? "无法发起 Shopify 授权。"); return; }
    window.location.assign(data.authorization_url);
  }
  async function syncShopify() {
    setConnectionError(""); setIsSyncing(true);
    const response = await fetch(`${API_BASE_URL}/v1/integrations/shopify/sync`, { method: "POST", headers: { Authorization: `Bearer ${accessToken}` } });
    if (response.status === 401) { sessionStorage.removeItem("revenueops_access_token"); setAccessToken(""); setIsSyncing(false); setConnectionError("登录已过期，请重新登录后再同步。"); return; }
    const data = await response.json().catch(() => ({}));
    setIsSyncing(false);
    if (!response.ok || !data.connection) { setConnectionError(data.error ?? "首次同步失败，请稍后重试。"); return; }
    rememberShopifyConnection(data.connection);
  }
  function suggestCsvColumn(columns: string[], names: string[]) {
    const lowered = new Map(columns.map((column) => [column.toLowerCase(), column]));
    return names.map((name) => lowered.get(name)).find(Boolean) ?? "";
  }
  async function previewCsv() {
    if (!accessToken) { setCsvMessage("请先登录；CSV 只会进入当前账号的工作区。"); return; }
    if (!csvFile) { setCsvMessage("请先选择一个订单 CSV 文件。文件尚未上传。"); return; }
    setCsvMessage(""); setIsCsvBusy(true);
    const form = new FormData(); form.append("file", csvFile);
    const response = await fetch(`${API_BASE_URL}/v1/data-sources/csv/preview`, { method: "POST", headers: { Authorization: `Bearer ${accessToken}` }, body: form });
    const data = await response.json().catch(() => ({})); setIsCsvBusy(false);
    if (response.status === 401) { sessionStorage.removeItem("revenueops_access_token"); setAccessToken(""); setCsvMessage("登录已失效，请在此重新登录后继续检查安全文件。"); return; }
    if (!response.ok) { setCsvMessage(data.error ?? "无法读取 CSV 结构。"); return; }
    const columns = Array.isArray(data.columns) ? data.columns : [];
    setCsvPreview({ columns, row_count: Number(data.row_count ?? 0) });
    setCsvMapping({ order_id: suggestCsvColumn(columns, ["order_id", "id", "order_number"]), ordered_at: suggestCsvColumn(columns, ["ordered_at", "created_at", "order_date", "date"]), total_amount: suggestCsvColumn(columns, ["total_amount", "total_price", "amount", "revenue"]), customer_id: suggestCsvColumn(columns, ["customer_id", "customer"]), marketing_consent: suggestCsvColumn(columns, ["marketing_consent", "accepts_marketing", "subscribed"]) });
    setCsvMessage(`已读取 ${Number(data.row_count ?? 0).toLocaleString()} 行与 ${columns.length} 个列名；服务端没有回传订单内容。`);
  }
  async function chooseShopifyCsv(file: File | null) {
    if (!file) return;
    setCsvMessage("正在浏览器本地删除敏感列并生成匿名客户 ID…"); setIsCsvBusy(true);
    try { setCsvFile(await sanitizeShopifyOrders(file)); setCsvPreview(null); setCsvMessage("本地清洗完成：原始 Email、电话、姓名、地址不会上传。现在可检查安全文件结构。"); }
    catch (error) { setCsvFile(null); setCsvMessage(error instanceof Error ? error.message : "本地清洗失败。"); }
    finally { setIsCsvBusy(false); }
  }
  async function importCsv() {
    if (!csvFile || !csvPreview) return;
    if (!csvMapping.order_id || !csvMapping.ordered_at || !csvMapping.total_amount) { setCsvMessage("请完成订单号、下单时间和订单金额的映射。"); return; }
    setCsvMessage(""); setIsCsvBusy(true);
    const form = new FormData(); form.append("file", csvFile); form.append("display_name", csvFile.name.replace(/\.csv$/i, ""));
    form.append("mapping", JSON.stringify(csvMapping)); form.append("defaults", JSON.stringify({ currency: "USD", market: "GLOBAL", timezone: "UTC" }));
    const response = await fetch(`${API_BASE_URL}/v1/data-sources/csv/import`, { method: "POST", headers: { Authorization: `Bearer ${accessToken}` }, body: form });
    const data = await response.json().catch(() => ({})); setIsCsvBusy(false);
    if (response.status === 401) { sessionStorage.removeItem("revenueops_access_token"); setAccessToken(""); setCsvMessage("登录已失效，请在此重新登录后继续导入安全文件。"); return; }
    if (!response.ok) { setCsvMessage(data.error ?? "导入失败，请检查字段映射。"); return; }
    setCsvMessage(`已导入 ${Number(data.source?.record_count ?? 0).toLocaleString()} 笔有效订单；客户标识已在服务端匿名化。`);
    setCsvFile(null); setCsvPreview(null);
  }
  const shopifyReady = shopifyReadiness?.state === "ready_to_authorize";
  const shopifyConnected = Boolean(shopifyConnection);
  return <main className="page-content"><PageHeading eyebrow="Data foundation" title="数据连接" description="跨境商家的真实价值来自可授权的数据连接，而不是替代商家保存或猜测业务数据。" action={<button className="button button-primary" onClick={() => document.getElementById("connectors")?.scrollIntoView({ behavior: "smooth" })}>申请连接器</button>} />
  <section className="notice-bar"><span className="notice-dot" />当前运行在示例工作区。连接真实店铺前，应由商家授权并明确数据范围、用途与保留周期。{shopifyConnected ? <strong> Shopify 已连接：{shopifyConnection?.shop_domain}{shopifyConnection?.last_synced_at ? " · 已完成汇总同步" : " · 等待首次同步"}</strong> : shopifyReadiness && <strong> Shopify OAuth：{shopifyReady ? "可开始授权" : "等待应用配置"}</strong>}</section>
  <section className="data-layout"><article className="card"><div className="card-kicker"><span>CONNECTION STATUS</span><StatusBadge tone="neutral">DEMO WORKSPACE</StatusBadge></div><h2>数据域覆盖</h2><div className="data-table">{sources.map(([name, state, source, note]) => <div className="data-row" key={name}><div><strong>{name}</strong><small>{note}</small></div><StatusBadge tone={state === "已接入" ? "success" : "neutral"}>{state}</StatusBadge><span>{source}</span></div>)}</div></article><aside className="card data-contract"><p className="eyebrow">Principles</p><h3>连接原则</h3><ol><li>商家在自己的渠道平台授权。</li><li>最小化获取字段与访问范围。</li><li>明确数据更新频率和失效机制。</li><li>每一项 Agent 建议都可追溯数据来源。</li></ol></aside></section>
  <section className="card api-card"><div><p className="eyebrow">NEXT MILESTONE</p><h2>{shopifyConnection?.summary ? shopifyConnection.summary.is_development_store ? "Shopify 开发店同步验证完成" : "Shopify 汇总数据已可用" : "从样本到真实商家数据"}</h2><p>{shopifyConnection?.summary ? `${shopifyConnection.summary.is_development_store ? "当前为 Shopify 开发店：只用于验证同步，不能解锁真实机会建模或客户触达。" : ""}已同步聚合计数：订单 ${shopifyConnection.summary.orders}、客户 ${shopifyConnection.summary.customers}、产品 ${shopifyConnection.summary.products}、库存项 ${shopifyConnection.summary.inventory_items}（最多读取 250 项）${shopifyConnection.summary.currency_code ? `（${shopifyConnection.summary.currency_code}）` : ""}。${shopifyConnection.comparison ? `较上次同步：订单 ${shopifyConnection.comparison.deltas.orders >= 0 ? "+" : ""}${shopifyConnection.comparison.deltas.orders}、客户 ${shopifyConnection.comparison.deltas.customers >= 0 ? "+" : ""}${shopifyConnection.comparison.deltas.customers}、产品 ${shopifyConnection.comparison.deltas.products >= 0 ? "+" : ""}${shopifyConnection.comparison.deltas.products}、库存项 ${shopifyConnection.comparison.deltas.inventory_items >= 0 ? "+" : ""}${shopifyConnection.comparison.deltas.inventory_items}。` : "当前为首次同步基线。"}未保存订单、客户、设备级原始数据。` : "第一阶段优先接入 Shopify 的汇总指标；不会保存邮箱、电话、地址、IP 或浏览器信息。"}</p></div><span className="api-tag">{shopifyConnection?.summary ? "AGGREGATES SYNCED" : "API CONTRACT READY"}</span></section>
  <section className="card connector-card"><div className="card-heading"><div><p className="eyebrow">PILOT ORDER IMPORT</p><h2>Shopify 订单的本地隐私清洗</h2><p>选择 Shopify 订单导出后，浏览器先删除敏感列并生成匿名客户 ID；只有清洗后的新 CSV 才会上传。</p></div><StatusBadge tone="accent">需登录</StatusBadge></div>{!accessToken && <div className="connector-auth"><input aria-label="CSV 导入用户名" placeholder="账号" value={username} onChange={(event) => setUsername(event.target.value)} /><input aria-label="CSV 导入密码" type="password" placeholder="密码" value={password} onChange={(event) => setPassword(event.target.value)} /><button className="small-primary" onClick={loginForConnection}>登录后导入</button></div>}<div className="connector-auth"><input aria-label="Shopify 订单 CSV 文件" type="file" accept=".csv,text/csv" onChange={(event) => chooseShopifyCsv(event.target.files?.[0] ?? null)} /><button className="small-primary" disabled={isCsvBusy || !csvFile} onClick={previewCsv}>{isCsvBusy ? "正在本地清洗…" : "检查安全文件结构"}</button></div>{csvPreview && <div className="scope-grid"><label><span>订单号 *</span><select value={csvMapping.order_id ?? ""} onChange={(event) => setCsvMapping({ ...csvMapping, order_id: event.target.value })}><option value="">请选择列</option>{csvPreview.columns.map((column) => <option key={column} value={column}>{column}</option>)}</select></label><label><span>下单时间 *</span><select value={csvMapping.ordered_at ?? ""} onChange={(event) => setCsvMapping({ ...csvMapping, ordered_at: event.target.value })}><option value="">请选择列</option>{csvPreview.columns.map((column) => <option key={column} value={column}>{column}</option>)}</select></label><label><span>订单金额 *</span><select value={csvMapping.total_amount ?? ""} onChange={(event) => setCsvMapping({ ...csvMapping, total_amount: event.target.value })}><option value="">请选择列</option>{csvPreview.columns.map((column) => <option key={column} value={column}>{column}</option>)}</select></label><label><span>匿名客户 ID（可选）</span><select value={csvMapping.customer_id ?? ""} onChange={(event) => setCsvMapping({ ...csvMapping, customer_id: event.target.value })}><option value="">不导入</option>{csvPreview.columns.map((column) => <option key={column} value={column}>{column}</option>)}</select></label><label className="scope-wide"><span>营销同意状态（可选；真实触达前必需）</span><select value={csvMapping.marketing_consent ?? ""} onChange={(event) => setCsvMapping({ ...csvMapping, marketing_consent: event.target.value })}><option value="">不导入</option>{csvPreview.columns.map((column) => <option key={column} value={column}>{column}</option>)}</select></label></div>}{csvPreview && <button className="small-primary" disabled={isCsvBusy} onClick={importCsv}>{isCsvBusy ? "正在导入…" : "导入到我的试点工作区"}</button>}{csvMessage && <p className="connector-modal-note" role="status">{csvMessage}</p>}{connectionError && <p className="connector-error" role="alert">{connectionError}</p>}</section>
  <section className="card connector-card" id="connectors"><div className="card-heading"><div><p className="eyebrow">AUTHORIZED SOURCES</p><h2>选择一个真实数据源</h2><p>先查看授权范围与接入准备度；不会自动读取或发送任何数据。</p></div><StatusBadge tone="accent">商家可控</StatusBadge></div><div className="connector-grid">{connectors.map((connector) => <div className="connector-item" key={connector.name}><div className="connector-top"><span className="connector-logo">{connector.icon}</span><div><strong>{connector.name}</strong><small>{connector.type}</small></div></div><p>{connector.detail}</p><button className="connector-details-button" onClick={() => setSelected(connector)}>查看授权范围</button><button className="connector-button" onClick={() => setSelected(connector)}>{connector.name === "Shopify" ? (shopifyConnected ? "管理已连接店铺" : shopifyReady ? "准备开始授权" : "查看接入准备") : "规划中"}</button></div>)}</div><div className="connection-workflow"><p className="eyebrow">CONNECTION WORKFLOW</p><div className="workflow-steps"><span className="workflow-step-active">应用准备</span><span className={shopifyConnected ? "workflow-step-active" : ""}>商家 OAuth 授权</span><span className={shopifyConnection?.last_synced_at ? "workflow-step-active" : ""}>首次同步</span><span className={shopifyConnection?.summary ? "workflow-step-active" : ""}>数据可用</span></div></div></section>
  {selected && <div className="connector-modal-backdrop" role="presentation" onClick={() => setSelected(null)}><section className="connector-modal" role="dialog" aria-modal="true" aria-labelledby="connector-dialog-title" onClick={(event) => event.stopPropagation()}><div className="connector-modal-header"><div><p className="eyebrow">CONNECTION REVIEW</p><h2 id="connector-dialog-title">{selected.name} 授权范围</h2></div><button className="connector-close" aria-label="关闭授权范围" onClick={() => setSelected(null)}>×</button></div><p className="connector-modal-intro">商家将在 {selected.name} 官方页面完成 OAuth 授权。RevenueOps 只请求必要的只读权限。</p><div className="scope-grid"><div><span>访问权限</span><strong>{selected.access}</strong></div><div><span>同步频率</span><strong>{selected.frequency}</strong></div><div className="scope-wide"><span>请求字段</span><strong>{selected.fields}</strong></div><div className="scope-wide"><span>使用目的</span><strong>{selected.purpose}</strong></div></div><div className="connector-modal-note">{selected.name === "Shopify" && shopifyConnection ? `已连接 ${shopifyConnection.shop_domain}${shopifyConnection.last_synced_at ? "，汇总同步已完成。" : "，可开始首次汇总同步。"}` : selected.name === "Shopify" ? (shopifyReadiness?.message ?? "正在检查 Shopify 应用准备度。") : "该连接器尚未进入实施阶段。"}</div>{selected.name === "Shopify" && shopifyReady && <div className="connector-auth">{!accessToken ? <><input aria-label="登录用户名" placeholder="账号（3-32 位英文、数字、_ 或 -）" value={username} onChange={(event) => setUsername(event.target.value)} /><input aria-label="登录密码" type="password" placeholder="密码（至少 8 位）" value={password} onChange={(event) => setPassword(event.target.value)} />{isRegistering && <input aria-label="注册链接码" type="password" placeholder="邀请码" value={registrationCode} onChange={(event) => setRegistrationCode(event.target.value)} />}<button className="small-primary" onClick={isRegistering ? registerForConnection : loginForConnection}>{isRegistering ? "创建账号后连接" : "登录后连接"}</button><button className="connector-details-button" onClick={() => setIsRegistering(!isRegistering)}>{isRegistering ? "已有账号？登录" : "首次使用？创建账号"}</button></> : shopifyConnection ? <button className="small-primary" disabled={isSyncing} onClick={syncShopify}>{isSyncing ? "正在同步汇总数据…" : shopifyConnection.last_synced_at ? "重新同步汇总数据" : "开始首次汇总同步"}</button> : <><input aria-label="Shopify 店铺域名" placeholder="your-store.myshopify.com" value={shopDomain} onChange={(event) => setShopDomain(event.target.value)} /><button className="small-primary" onClick={beginShopifyAuthorization}>前往 Shopify 授权</button></>}</div>}{connectionError && <p className="connector-error" role="alert">{connectionError}</p>}<button className="connector-details-button" onClick={() => setSelected(null)}>关闭</button></section></div>}
</main>; }
