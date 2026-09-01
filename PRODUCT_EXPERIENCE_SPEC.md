# Olist RevenueOps Console — Product Experience Specification

**Version:** 1.0  
**Audience:** Cross-border DTC merchants, growth operators, and retention leads  
**Product principle:** A merchant should understand the next revenue decision before they ever see a raw chart.

## 1. Experience promise

Olist RevenueOps is not an analytics dashboard with an embedded chatbot. It is a decision workspace for merchants who need to turn customer and order signals into accountable retention actions.

In one session, an operator should be able to answer:

1. What is the highest-value revenue opportunity right now?
2. Why should I trust it?
3. What customer segment, market, language, channel and offer should I use?
4. What must I approve before anything happens?
5. Did the action create incremental revenue, in which currency and attribution window?

## 2. Primary user flow

```text
Connect data
   -> Understand readiness
   -> Review ranked opportunities
   -> Open an opportunity
   -> Create / edit campaign brief
   -> Human approval
   -> Simulated or observed result
   -> Learning and next-best action
```

The Agent is an assistant inside each decision moment. It is not a separate destination that forces users to formulate the right question.

## 3. Information architecture

| Navigation | User intent | Primary output |
|---|---|---|
| **Overview** | “What needs my attention?” | Revenue opportunity queue, key business state, readiness |
| **Opportunities** | “What should we do next?” | Evidence-backed opportunity cards, impact and confidence |
| **Campaigns** | “What is approved or waiting?” | Campaign brief, approval state, execution / result status |
| **Learning** | “What worked?” | Results segmented by market, channel, strategy and currency |
| **Data** | “Can I safely trust this?” | Connection, coverage, currency, consent and sync readiness |

The legacy free-form Agent chat remains under **Ask Agent** as a secondary capability. It must never be the page that represents the entire product.

## 4. Overview layout

### Header

- Brand: `Olist RevenueOps`
- Workspace name and connected-source state
- Global time context (e.g. `Reporting in UTC · Market: US`)
- Data state badge: `Sample`, `Imported`, `Connected`, or `Needs attention`

### First viewport

1. **Revenue at risk** — value, currency, evidence period, and whether it is estimated;
2. **Top opportunity** — one action recommendation with an explicit review CTA;
3. **Campaign health** — drafts, awaiting approval, active, and results due;
4. **Validated incremental revenue** — only observed results, never simulations.

### Secondary content

- Ranked opportunities; 
- Data readiness / consent warning, only when blocking execution;
- An “Ask Agent” shortcut tied to the selected opportunity.

No generic region, payment, or RFM chart appears by default. Detail charts are revealed only when a connected source supports their data model.

## 5. Opportunity card specification

Every opportunity is a self-contained decision unit:

| Field | Requirement |
|---|---|
| Opportunity title | Business-language statement, not a technical anomaly |
| Potential impact | Currency-qualified, period-bound, and labelled estimate/observed |
| Audience | Pseudonymous segment definition, never raw contacts |
| Evidence | At least one metric, data source, and coverage period |
| Recommendation | Channel, market, locale, offer hypothesis, and test window |
| Trust state | Data completeness and confidence, with missing-field blockers |
| CTA | `Review campaign` or `Ask Agent` |

## 6. Campaign workspace specification

Campaigns are created from an opportunity whenever possible. The form is organized in four steps, not a long generic form:

1. **Audience** — eligibility rule, estimated count, consent readiness, control holdout;
2. **Message & offer** — channel, market, locale, content, incentive hypothesis;
3. **Measurement** — attribution window, currency, costs, refund treatment;
4. **Approval** — human approver, execution mode, immutable audit summary.

`Simulation` is a first-class mode with a visible badge. It must never look like live outreach.

## 7. Learning specification

Learning is not a historical task list. It answers whether strategies created value.

- Separate `Observed` from `Simulation` at the first filter;
- Never aggregate different currencies without a named FX policy;
- Show treatment/control conversion, incremental orders, incremental revenue, cost, and ROI;
- Show data-quality caveats: attribution window, refund treatment, and sample size;
- Produce a next-best-action recommendation only after presenting the observed evidence.

## 8. Visual system

### Tone

Calm, operational, and premium. Avoid “AI magic” gradients, emoji-heavy labels, or dense dashboard chrome.

### Foundation

- Background: deep ink / off-white neutral surfaces; 
- Accent: restrained blue-green used only for primary actions and positive verified outcomes;
- Risk: amber/red only for decision-relevant warnings;
- Typography: Inter-style sans-serif, high contrast, compact but breathable;
- Layout: 12-column desktop grid, 24px minimum section gaps, cards used for decisions rather than every text block;
- Badges: `SAMPLE`, `IMPORTED`, `SIMULATION`, `OBSERVED`, `ACTION REQUIRED`.

### Content rules

- English is the default merchant-facing language; a future locale setting may translate it;
- Never show `R$` outside Olist sample mode;
- Write “Estimated incremental revenue” rather than “Revenue” when it is modelled;
- Show the evidence period next to every metric that may be interpreted as current;
- Explain missing data in product terms: `Customer consent is not connected — campaign export is unavailable.`

## 9. Acceptance criteria for this redesign

The redesign is acceptable only when:

1. A first-time user can identify the primary product value in the first viewport without opening chat;
2. No merchant-connected page mixes Olist demo metrics with merchant metrics;
3. Every money metric carries a currency and every result carries a mode;
4. A user can distinguish recommendation, approved activity, simulation, and observed result at a glance;
5. Every execution-related control states its human-approval and consent boundary;
6. The interface contains no framework/model names in primary user-facing content;
7. Legacy charts and technical diagnostic details are progressively disclosed, not the default surface.

