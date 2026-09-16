import type { Metadata } from "next";
import Link from "next/link";
import styles from "./sample-report.module.css";

export const metadata: Metadata = {
  title: "示例诊断报告 | RevenueOps 试点",
  description: "查看 RevenueOps 只读收入诊断的交付结构、判断边界与商家审批流程。",
};

const snapshot = [
  { label: "订单", value: "2", note: "开发店聚合数量" },
  { label: "客户", value: "3", note: "不保存身份信息" },
  { label: "产品", value: "17", note: "只读汇总同步" },
  { label: "库存项", value: "26", note: "店铺币种 USD" },
];

export default function SampleReportPage() {
  return (
    <main className={`${styles.page} page-content`}>
      <nav className={styles.backNav} aria-label="返回试点计划">
        <Link href="/pilot">← 返回试点计划</Link>
        <span>交付样例 · v1.0</span>
      </nav>

      <header className={styles.hero}>
        <div className={styles.heroCopy}>
          <p className={styles.kicker}>Merchant diagnostic preview</p>
          <h1>一份商家真正能拿走的收入诊断</h1>
          <p className={styles.lead}>不是一屏漂亮数字，而是一条可以审阅、批准、执行和复盘的决策路径。</p>
        </div>
        <div className={styles.reportMeta} aria-label="报告属性">
          <span>只读数据</span>
          <span>单一问题</span>
          <span>商家审批</span>
        </div>
      </header>

      <aside className={styles.demoNotice}>
        <strong>演示数据，不代表真实商业结果</strong>
        <span>下方“连接快照”来自当前开发店聚合计数；“诊断样例”使用合成场景，仅展示交付方法。</span>
      </aside>

      <section className={styles.section} aria-labelledby="snapshot-title">
        <div className={styles.sectionHeading}>
          <div>
            <p className={styles.index}>01 / DATA HEALTH</p>
            <h2 id="snapshot-title">连接验证快照</h2>
          </div>
          <span className={`${styles.badge} ${styles.badgeWarning}`}>样本不足，暂不下商业结论</span>
        </div>
        <div className={styles.metricGrid}>
          {snapshot.map((item) => (
            <article className={styles.metric} key={item.label}>
              <span>{item.label}</span>
              <strong>{item.value}</strong>
              <small>{item.note}</small>
            </article>
          ))}
        </div>
        <div className={styles.healthSummary}>
          <div>
            <span className={styles.healthLight} aria-hidden="true" />
            <strong>技术连接已通过</strong>
          </div>
          <p>同步链路可用，但订单量低于诊断门槛。正式试点至少需要 20 笔订单、3 个活跃日期和单一币种。</p>
        </div>
      </section>

      <section className={styles.section} aria-labelledby="diagnosis-title">
        <div className={styles.sectionHeading}>
          <div>
            <p className={styles.index}>02 / DIAGNOSIS SAMPLE</p>
            <h2 id="diagnosis-title">合成诊断样例</h2>
          </div>
          <span className={`${styles.badge} ${styles.badgeDemo}`}>以下全部为演示场景</span>
        </div>

        <div className={styles.diagnosisGrid}>
          <article className={styles.finding}>
            <div className={styles.findingTopline}>
              <span>优先问题</span>
              <strong>P0</strong>
            </div>
            <h3>最近 7 天净销售额下降 25%</h3>
            <p>演示口径：最近 7 天 USD 7,500，对比前 7 天 USD 10,000。该信号只用于决定“值得进一步验证什么”，不直接证明原因。</p>
            <div className={styles.delta}>
              <span>趋势变化</span>
              <strong>−25%</strong>
              <small>合成示例</small>
            </div>
          </article>

          <article className={styles.evidence}>
            <p className={styles.index}>证据边界</p>
            <h3>我们知道什么，也明确不知道什么</h3>
            <dl>
              <div><dt>可确认</dt><dd>两个等长时间窗的净销售额存在下降。</dd></div>
              <div><dt>不可确认</dt><dd>下降由复购、流量、库存或季节性中的哪一项造成。</dd></div>
              <div><dt>下一证据</dt><dd>在商家批准后，以最小范围验证一个原因。</dd></div>
            </dl>
          </article>
        </div>
      </section>

      <section className={styles.section} aria-labelledby="experiment-title">
        <div className={styles.sectionHeading}>
          <div>
            <p className={styles.index}>03 / RECOMMENDED TEST</p>
            <h2 id="experiment-title">建议验证：沉默客户再激活</h2>
          </div>
          <span className={`${styles.badge} ${styles.badgeSuccess}`}>需商家批准后执行</span>
        </div>

        <div className={styles.experimentGrid}>
          <article>
            <span>目标人群</span>
            <strong>90 天未复购且已同意营销的客户</strong>
            <p>仅使用匿名分群计数；RevenueOps 不保存客户姓名、邮箱或电话。</p>
          </article>
          <article>
            <span>实验设计</span>
            <strong>14 天小流量测试 + 对照组</strong>
            <p>渠道、文案、预算和触达名单均由商家确认，系统不会自动群发。</p>
          </article>
          <article>
            <span>唯一指标</span>
            <strong>增量净销售额</strong>
            <p>对比实验组与对照组，不把自然回购错误归因为本次活动。</p>
          </article>
          <article>
            <span>决策日期</span>
            <strong>启动后第 14 天</strong>
            <p>达到商家预设门槛才扩大；无明显增量则停止或修改假设。</p>
          </article>
        </div>

        <details className={styles.disclosure}>
          <summary>查看计算口径与停止条件</summary>
          <div>
            <p><strong>增量净销售额</strong> = 实验组人均净销售额 − 对照组人均净销售额，再乘以实验组人数。</p>
            <p><strong>停止条件</strong>：数据异常、商家撤回批准、无合规营销同意，或达到商家预设的成本上限。</p>
          </div>
        </details>
      </section>

      <section className={`${styles.section} ${styles.delivery}`} aria-labelledby="delivery-title">
        <div className={styles.sectionHeading}>
          <div>
            <p className={styles.index}>04 / DELIVERY</p>
            <h2 id="delivery-title">试点结束时，商家会收到什么</h2>
          </div>
        </div>
        <ol className={styles.deliveryList}>
          <li><span>01</span><div><strong>一页诊断摘要</strong><p>数据健康度、一个优先问题和证据边界。</p></div></li>
          <li><span>02</span><div><strong>一份审批清单</strong><p>受众、渠道、预算、停止条件与数据保留方式。</p></div></li>
          <li><span>03</span><div><strong>一份实验复盘</strong><p>结果、增量口径、限制条件，以及继续、调整或停止建议。</p></div></li>
        </ol>
      </section>

      <section className={styles.cta}>
        <div>
          <p className={styles.kicker}>Controlled pilot</p>
          <h2>先验证一件小事，再决定是否继续</h2>
          <p>7 天只读诊断；不自动触达客户，不承诺特定营收结果。</p>
        </div>
        <div className={styles.ctaActions}>
          <Link className="button button-primary" href="/pilot#apply">申请免费试点</Link>
          <Link className="button button-ghost" href="/privacy">查看数据条款</Link>
        </div>
      </section>
    </main>
  );
}
