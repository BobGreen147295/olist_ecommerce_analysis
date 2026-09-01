# Olist RevenueOps Web

面向跨境 DTC 商家的独立运营工作台前端。它把 AI 发现的收入机会、人工审批的活动实验、结果归因和数据接入状态放在同一个可审计界面中。

## 当前范围

- `Overview`：今日优先收入机会与数据准备度。
- `Opportunities`：基于影响、潜力、置信度和可执行性排序的机会队列。
- `Campaigns`：人工审批优先的活动草案与操作留痕；不自动触达客户。
- `Learning`：严格区分已观测实验结果和模拟预估。
- `Data`：面向 Shopify、Klaviyo/Braze、广告平台和 ERP 的数据接入路径。

当前页面数据均为明确标注的示例数据，不代表真实商家经营结果。后端 API 契约见 [API_CONTRACT.md](./API_CONTRACT.md)。

## 本地运行

```bash
cd web
npm install
npm run dev
```

打开 `http://localhost:3000`。生产校验使用：

```bash
npm run build
```

## 下一阶段

将 Python Agent 与 PostgreSQL/Supabase 封装为服务端 API，再以真实商家授权数据替换示例数据；浏览器端不会持有数据库连接串或服务密钥。
