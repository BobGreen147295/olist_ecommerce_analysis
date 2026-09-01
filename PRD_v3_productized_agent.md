# Cross-border AI Revenue Operations Agent

**Version**: v4.0
**Status**: Product-definition baseline
**Product name (working title)**: Olist RevenueOps Agent

## 1. First principle

This product does not sell a chatbot, a dashboard, or a historical dataset. It helps cross-border DTC merchants produce measurable business results.

> For an authorized merchant, identify a revenue opportunity, prepare an auditable campaign, wait for human approval, measure incremental impact, and use the outcome to improve the next action.

The only meaningful product loop is:

```text
Authorized commerce data
  -> opportunity detection
  -> evidence-backed recommendation
  -> merchant review and approval
  -> channel-ready campaign package
  -> delivery / result import
  -> incrementality and ROI measurement
  -> next-best action
```

The product is initially built for Shopify-based cross-border DTC merchants serving overseas consumers. It is not positioned as a generic Chinese marketplace analytics tool.

## 2. Target users and job to be done

### Primary user: growth / retention operator at a cross-border DTC brand

- Runs a Shopify storefront and uses email, SMS, or WhatsApp-style owned channels;
- Has order data but lacks time or analytical depth to segment customers and design controlled experiments;
- Needs an explainable recommendation, an approval checkpoint, and an outcome they can defend to a manager.

### Economic buyer: founder, head of growth, or ecommerce manager

- Wants incremental revenue, repeat purchase, and lower wasted discount spend;
- Will only authorize data access if permissions are minimal, reversible, and the expected return is credible.

### First job to be done

> When valuable customers become inactive, help me decide whom to re-engage, with which localized message and incentive, through which channel, and prove whether the action created incremental revenue.

## 3. Product wedge: high-value customer reactivation

V1 deliberately focuses on one narrow, measurable loop:

1. Detect high-value customers who have become inactive;
2. Form an eligible, consented audience and a holdout/control group;
3. Produce localized campaign copy and an execution package for a connected channel;
4. Require merchant approval before any external delivery;
5. Ingest delivery and conversion results;
6. Calculate incremental orders, incremental revenue, cost, and ROI with an explicit attribution window.

The product may recommend. It must never send a campaign, issue a discount, alter budget, or contact a customer without an explicit merchant action.

## 4. Trust exchange and data-access strategy

Merchants do not grant access because the product says “AI.” They grant the minimum data required when the expected value exceeds the perceived risk and setup effort.

| Adoption stage | Merchant commitment | Product return |
|---|---|---|
| Experience | No merchant data; demo or generated data | Product walkthrough and transparent sample results |
| Safe trial | De-identified order CSV | First diagnostic and editable campaign plan |
| Connected trial | OAuth/API read scope to Shopify | Automated data refresh and continuous opportunity detection |
| Operating mode | Channel result sync, still merchant-approved delivery | Attributable revenue and next-best-action learning |

The first production connector is Shopify. CSV remains a deliberately lower-trust onboarding path, not the long-term core experience.

## 5. Canonical commerce data model

All connectors must map into a canonical model. A connector does not get to redefine business metrics.

### Orders (required for V1)

| Canonical field | Required | Definition |
|---|---:|---|
| `order_id` | Yes | Immutable source order identifier |
| `ordered_at` | Yes | ISO-8601 timestamp in UTC |
| `total_amount` | Yes | Final order amount in the order currency, after discounts and before/after tax only when explicitly declared |
| `currency` | Yes for cross-border production | ISO 4217 currency code, e.g. USD, GBP, EUR |
| `customer_id` | Recommended | Stable pseudonymous customer identifier |
| `market` | Recommended | Selling market / country or region code, e.g. US, GB, DE |
| `timezone` | Recommended | IANA timezone used for local campaign scheduling |
| `status` | Recommended | Paid/fulfilled/cancelled/refunded source status |

### Customers and consent (required before real outbound execution)

- Stable pseudonymous customer ID, never a prompt-time need for raw email or phone number;
- Marketing consent state and consent updated time;
- Locale / preferred language and market;
- Suppression and unsubscribe state;
- Raw contact details stay in the execution platform. The agent receives only the fields needed for segmentation and content selection.

### Campaign and outcome (required for ROI claims)

- Campaign ID, channel, market, locale, send time, attribution window, treatment/control audience size;
- Incentive cost and non-incentive channel cost;
- Delivery, conversion, order, and revenue outcomes;
- Currency and FX conversion source if results are aggregated across currencies.

## 6. Metrics and attribution rules

- **Treatment conversion rate** = treatment orders / treatment eligible recipients;
- **Control conversion rate** = control orders / control eligible customers;
- **Incremental orders** = treatment recipients × (treatment conversion rate − control conversion rate);
- **Incremental revenue** = incremental orders × control-group AOV;
- **ROI** = (incremental revenue − campaign cost) / campaign cost.

An ROI is only comparable within the same currency. Cross-currency portfolio reporting must either keep markets separate or state an FX source, rate date, and reporting currency. The interface must never label a simulated result as an actual business outcome.

Every completed campaign result must record an attribution window, treatment/control eligibility rule, whether revenue is net of returns/refunds, currency, and observed vs simulated mode.

## 7. Safety, privacy, and compliance by design

- OAuth scopes and uploaded fields use the minimum necessary access;
- merchants can disconnect a source and request deletion of imported data;
- no automatic outreach; delivery always has an approval boundary;
- no contact of people without a marketing-consent signal from the source system;
- audience exports are pseudonymous by default and time-bound;
- prompts and diagnostic logs do not include raw email, phone, full address, or payment data;
- every recommendation shows source, coverage period, data completeness, and whether it is sample, simulated, or observed data;
- regulatory implementation must be reviewed with counsel before production deployment in relevant markets.

## 8. Product flow

```text
Shopify / CSV / future analytics connection
        ↓
Data validation: currency, time zone, order status, coverage, consent availability
        ↓
Deterministic opportunity detection
        ↓
Agent explanation + localized campaign draft
        ↓
Merchant edits audience, channel, language, offer, budget, attribution window
        ↓
Merchant approval
        ↓
Export / connected-channel handoff (never automatic in V1)
        ↓
Outcome import and controlled-experiment measurement
        ↓
Campaign learning record and next-best action
```

## 9. Current implementation and non-claims

The repository provides an authenticated Streamlit product, PostgreSQL persistence, CSV order import, deterministic analysis tools, proactive alerts, editable operation tasks, simulated campaign records, A/B result calculation, feedback operations, and regression evaluation.

It does **not** yet provide Shopify OAuth, customer-consent ingestion, live Email/SMS/WhatsApp delivery, or an observed-result connector. It must be described as a **cross-border RevenueOps prototype with a simulated execution loop**, not as a production marketing automation platform.

Olist data is retained only as a transparent demonstration and regression baseline when no merchant data source is connected.

## 10. Delivery roadmap

### Phase A — Cross-border foundation (this iteration)

- [x] Canonical order CSV connection
- [ ] Require/order-protect currency, market, timezone and order-status metadata
- [ ] Store campaign locale, attribution window, execution mode, and result currency
- [ ] Replace Olist-first product language with cross-border DTC language
- [ ] Clearly label sample / imported / simulated / observed data states

### Phase B — Shopify connected trial

- Shopify OAuth installation and minimum read scopes;
- Incremental orders/customer/product sync;
- Shopify data-quality and consent-readiness checks;
- Automatic refresh, source health, and disconnect/delete controls.

### Phase C — Human-approved activation

- Klaviyo (first) campaign/audience handoff;
- localized email draft, suppression-aware audience export, and approval log;
- campaign delivery/result import;
- observed vs simulated outcome separation.

### Phase D — Revenue learning system

- market-level holdout experimentation;
- refund-adjusted revenue and explicit FX reporting;
- strategy-performance learning by segment, channel, incentive, locale, and season;
- pricing based on subscription plus verified outcome/value tier.

## 11. Success criteria

Product success is not number of chat sessions. Each phase has an economic proof point:

| Phase | Evidence of progress |
|---|---|
| Connected trial | A merchant or test store completes validated data connection within 15 minutes |
| First value | A user saves and approves a campaign plan that is grounded in their data |
| Activation | A merchant exports or hands off an approved eligible audience without violating consent constraints |
| Outcome | At least one campaign has attributable treatment/control results with explicit currency and window |
| Commercial validation | A pilot merchant repeats the loop because the decision or result is valuable enough to pay for |
