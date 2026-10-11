// Deploy as an owner-executed Apps Script web app. Never uses GmailApp/inbox scopes.
// Store PILOT_NOTIFICATION_SECRET (32+ random characters) in Script Properties.
function doPost(e) {
  const reply = (value) => ContentService.createTextOutput(JSON.stringify(value))
    .setMimeType(ContentService.MimeType.JSON);
  let lock;
  try {
    if (!e || !e.postData || e.postData.contents.length > 1024) return reply({ok: false});
    const event = JSON.parse(e.postData.contents);
    const properties = PropertiesService.getScriptProperties();
    const secret = properties.getProperty('PILOT_NOTIFICATION_SECRET');
    if (!secret || secret.length < 32 || !/^[a-f0-9]{16}$/.test(event.application_id)
      || !Number.isInteger(event.timestamp) || Math.abs(Date.now() / 1000 - event.timestamp) > 300
      || !/^[a-f0-9]{64}$/.test(event.signature)) return reply({ok: false});
    const expected = Utilities.computeHmacSha256Signature(event.application_id + '.' + event.timestamp, secret)
      .map((b) => ('0' + (b & 255).toString(16)).slice(-2)).join('');
    let difference = 0;
    for (let i = 0; i < 64; i++) difference |= expected.charCodeAt(i) ^ event.signature.charCodeAt(i);
    if (difference) return reply({ok: false});
    lock = LockService.getScriptLock();
    if (!lock.tryLock(1000)) return reply({ok: false});
    const key = 'notification_' + event.application_id;
    const previous = properties.getProperty(key);
    if (previous) return reply({ok: previous.split(':')[0] === 'sent'});
    const now = Math.floor(Date.now() / 1000);
    const day = new Date().toISOString().slice(0, 10);
    const daily = properties.getProperty('notification_daily') || '';
    const count = daily.startsWith(day + ':') ? Number(daily.split(':')[1]) : 0;
    if (count >= 20 || MailApp.getRemainingDailyQuota() < 1) return reply({ok: false});
    // ponytail: bounded history; no retries after an ambiguous send. At 20/day,
    // retain 90 days of opaque IDs; use a durable queue only if volume requires it.
    for (const [name, value] of Object.entries(properties.getProperties())) {
      if (name.startsWith('notification_') && name !== 'notification_daily'
        && Number(value.split(':')[1]) < now - 90 * 86400) properties.deleteProperty(name);
    }
    properties.setProperty(key, 'attempted:' + now);
    properties.setProperty('notification_daily', day + ':' + (count + 1));
    MailApp.sendEmail({
      to: 'gbob4549@gmail.com',
      subject: 'RevenueOps 收到一条新试点申请',
      body: '申请编号：' + event.application_id
        + '\n请使用管理员账号查看：\nhttps://olist-revenueops.pages.dev/pilot/applications'
        + '\n\n此邮件不包含商家资料，也没有向申请人自动回复。',
      name: 'RevenueOps 申请提醒'
    });
    properties.setProperty(key, 'sent:' + now);
    return reply({ok: true});
  } catch (_) {
    // Do not echo exception text, incoming payloads or secrets.
    return reply({ok: false});
  } finally {
    if (lock && lock.hasLock()) lock.releaseLock();
  }
}

// Run once to request only send-mail authorization; this function sends nothing.
function authorizeNotifications() {
  return MailApp.getRemainingDailyQuota();
}
