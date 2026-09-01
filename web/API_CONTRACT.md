# Olist RevenueOps Web API Contract (v0.1)

网站目前使用明确标注的示例数据。下一阶段将由 Python Agent 服务提供以下只读 / 人工审批 API，前端不直接连接数据库。

| Endpoint | Purpose | Authorization |
| --- | --- | --- |
| `GET /api/v1/workspaces/{id}/overview` | 指标、数据健康度、今日首要机会 | workspace member |
| `GET /api/v1/opportunities` | Agent 发现的机会、证据、综合分 | workspace member |
| `POST /api/v1/campaigns/drafts` | 保存人工编辑后的活动草案 | operator |
| `POST /api/v1/campaigns/{id}/approve` | 记录人工批准，返回执行清单 | approver |
| `GET /api/v1/experiments/{id}/results` | 观测指标、对照组、归因假设 | workspace member |
| `GET /api/v1/data-connections` | 各数据域授权与同步状态 | workspace admin |

## Boundary

- `approve` 不应直接向营销渠道发送消息；渠道执行必须是独立、可配置、可撤销的步骤。
- 返回的每个机会必须含数据来源、时间范围、计算版本与置信度。
- 前端只通过服务端 API 获取数据；Supabase/PostgreSQL 连接串和服务密钥不进入浏览器。
- 所有金额、归因和预测结果均需带 `observed` 或 `simulated` 标签。
