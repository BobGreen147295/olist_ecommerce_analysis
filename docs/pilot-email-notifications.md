# 试点申请邮件提醒

公开联系邮箱和唯一通知收件人：`gbob4549@gmail.com`。不向申请人自动发送邮件。

## 已实现范围

- 表单成功表示申请已存入数据库，不表示邮件送达；不再承诺未经保障的两工作日响应。
- 保存成功之后，API 通过 HTTPS 调用 Google Apps Script。只传申请编号、时间戳和 HMAC 签名，不传商家邮箱、店铺、订单或客户资料。
- 脚本只使用 `MailApp` 发信，不使用 `GmailApp` 读取收件箱。收件人和邮件内容固定，请求不能选择收件人或注入正文。
- 必须同时安装 `scripts/appsscript.json`，显式限定唯一权限为 `https://www.googleapis.com/auth/script.send_mail`。不依赖自动推断权限；即使代码注释也可能影响 Google 的权限扫描。
- 签名有效期五分钟；脚本锁防并发重复，同一申请编号保留 90 天去重记录。每天最多尝试 20 封，并尊重 Google 剩余额度。
- 邮件失败、额度耗尽或超时不回滚申请，不自动重试。日志只记录状态和申请编号，不记录密钥、响应正文或回调网址。超时可能已发送，不能据此再次自动补发。
- 管理员列表显示通知是否配置；配置就绪和 Google 接受调用都不是收件箱送达证明。既有申请不自动补发。重复提交整个表单仍会生成新的申请，不属于同一编号去重。

## 启用（用户批准后）

1. 用 `gbob4549@gmail.com` 打开 Google Apps Script，新建项目，粘贴 `scripts/pilot-notification.gs`。在 Project Settings 勾选显示 `appsscript.json`，将 `scripts/appsscript.json` 的内容保存到该文件。已有项目保留其他设置，只把 `oauthScopes` 限定为上述唯一权限。回到 Overview 核实 Project OAuth Scopes 只有一项“Send email as you”；如果出现读取或删除邮件权限，立即停止授权。
2. 在项目设置的脚本属性中填写 `PILOT_NOTIFICATION_SECRET`：单独生成的至少 32 字符随机密钥。不要使用 Gmail/RevenueOps 密码，别写进源代码、聊天或 Git。
3. 关闭修改前的旧授权窗口，重新从该项目运行 `authorizeNotifications`，由账户本人核对并批准仅发信权限；该函数不发邮件。若出现未验证应用或安全警告，由用户本人决定是否继续，代理不绕过。收窄请求权限不等于撤销此前已授予的权限；如曾批准过全邮箱访问，须在 Google 账户的第三方连接中另行核对并撤销旧授权。
4. 部署 Web 应用：执行身份为自己，允许任何人访问（API 需要匿名 HTTPS 入口，但每次请求必须通过签名校验）。只有当前签名验证脚本版本可以部署；不要部署无鉴权示例。
5. 把 `/exec` 部署地址放入 Render `PILOT_NOTIFICATION_URL`；把同一密钥放入 `PILOT_NOTIFICATION_SECRET`。保存并重新部署。不得放入 `NEXT_PUBLIC_*`。
6. 前端生产构建把 `NEXT_PUBLIC_REVENUEOPS_CONTACT_EMAIL` 设为 `gbob4549@gmail.com`。若 Cloudflare 有旧 Outlook 覆盖值，需同时替换后重建。
7. 明确批准一次合成测试申请后，核对申请列表、Render 通知状态及 Gmail 收件。未收到邮件不能报告验收完成。

关闭：移除 Render 两项通知配置或停用脚本部署；申请表仍能保存，管理员仍能读取。

## 验证

- `python -m unittest discover -s tests -p test_pilot_notification.py`：合成数据、mock HTTP，绝不发送真实邮件。
- `node --test tests/pilot-notification.test.cjs`：运行实际 Apps Script 代码，mock Google 服务，验证签名、锁、去重、额度和无客户资料。
- `node --test web/tests/pilot-conversion.test.mjs web/tests/pilot-applications.test.mjs`：联系入口、提交反馈与管理员提示。

本方案不升级 Render、不接入付费邮件套餐。免费额度和可用性不是 SLA，超过上限需人工查看申请列表，不自动购买额度。

依据：[Render 免费服务 SMTP 限制](https://render.com/docs/free)、[MailApp 权限范围](https://developers.google.com/apps-script/reference/mail/mail-app)、[显式最小权限](https://developers.google.com/apps-script/concepts/scopes)、[授权与注释扫描](https://developers.google.com/apps-script/guides/services/authorization)、[Apps Script 配额](https://developers.google.com/apps-script/guides/services/quotas)、[Web 应用部署](https://developers.google.com/apps-script/guides/web)。
