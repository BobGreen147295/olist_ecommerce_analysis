type SyncConnection = {
  last_synced_at: string | null;
  opportunity_readiness?: { state: string };
  summary: { order_trend?: { truncated?: boolean }; pilot_order_sync?: { state: string } } | null;
};

export function ShopifySyncStatus({ connection, english }: { connection: SyncConnection; english: boolean }) {
  const tx = (zh: string, en: string) => english ? en : zh;
  const messages: Record<string, string> = {
    ready: tx("最近快照达到基础数据门槛，仍需确认分析口径；不代表持续同步或可以计算利润。", "The snapshot meets basic data checks. Confirm metric definitions; this is not continuous sync or a profit calculation."),
    development_store: tx("开发店：只能验证同步，不可当作真实商家效果。", "Development store: sync validation only, not real merchant results."),
    stale_data: tx("快照超过 24 小时，请手动重新同步；旧快照不代表当前经营状态。", "Snapshot is over 24 hours old. Resync manually; it does not represent current business conditions."),
    insufficient_data: tx("订单不足或汇总校验未通过，请检查覆盖范围后重新同步。", "Insufficient orders or aggregate validation failed. Check coverage and resync."),
    trend_required: tx("订单趋势尚未同步。连接成功或聚合计数不代表可以核对经营变化。", "Order trends have not been synced. A connection or aggregate count is not enough to verify business changes."),
    sync_required: tx("缺少可信同步时间，请手动重新同步。", "No trusted sync time. Resync manually."),
  };
  const parsed = connection.last_synced_at ? new Date(connection.last_synced_at) : null;
  const syncedAt = parsed && Number.isFinite(parsed.getTime()) ? parsed.toISOString() : null;
  const limited = connection.summary?.order_trend?.truncated || connection.summary?.pilot_order_sync?.state === "coverage_limit";
  return <section className="card api-card" aria-label={tx("Shopify 同步状态", "Shopify sync status")}><div>
    <h2>{tx("同步状态：手动更新，不自动补同步", "Sync status: manual updates only")}</h2>
    <p>{tx("最近成功同步（UTC）", "Last successful sync (UTC)")}: {syncedAt || tx("尚无可信记录", "No trusted record")}</p>
    <p role="status">{limited ? tx("同步覆盖存在截断，不能当作完整订单历史。请检查同步范围，不会自动重试。", "Sync coverage is truncated, not complete order history. Check the sync scope; no automatic retry is made.") : messages[connection.opportunity_readiness?.state || ""] || tx("同步结果尚未核实，请检查连接和数据覆盖。", "Sync results are unverified. Check connection and data coverage.")}</p>
    <p>{tx("同步失败时仅保留最近成功快照；错误不会被当作零订单或同步成功。到“管理已连接店铺”手动重试。", "A failed sync leaves only the last successful snapshot. Errors are not treated as zero orders or successful syncs. Retry manually in Manage connected store.")}</p>
  </div></section>;
}
