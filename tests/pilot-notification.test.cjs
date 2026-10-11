const {test} = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const crypto = require('node:crypto');
const source = fs.readFileSync(require('node:path').join(__dirname, '../scripts/pilot-notification.gs'), 'utf8');

function harness({quota = 100, locked = false, failSend = false} = {}) {
  const properties = new Map([['PILOT_NOTIFICATION_SECRET', crypto.randomBytes(32).toString('hex')]]);
  const sent = [];
  let held = false;
  const context = vm.createContext({Date, JSON, Number, Object, Math,
    ContentService: {MimeType: {JSON: 'json'}, createTextOutput: (text) => ({setMimeType: () => JSON.parse(text)})},
    PropertiesService: {getScriptProperties: () => ({getProperty: (key) => properties.get(key),
      setProperty: (key, value) => properties.set(key, value), deleteProperty: (key) => properties.delete(key),
      getProperties: () => Object.fromEntries(properties)})},
    LockService: {getScriptLock: () => ({tryLock: () => held = !locked, hasLock: () => held, releaseLock: () => held = false})},
    Utilities: {computeHmacSha256Signature: (value, key) => Array.from(crypto.createHmac('sha256', key).update(value).digest())},
    MailApp: {getRemainingDailyQuota: () => quota, sendEmail: (mail) => {sent.push(mail); if (failSend) throw new Error('ambiguous synthetic failure');}},
  });
  vm.runInContext(source, context);
  const event = (id = 'a'.repeat(16), overrides = {}) => {
    const timestamp = Math.floor(Date.now() / 1000);
    const signature = crypto.createHmac('sha256', properties.get('PILOT_NOTIFICATION_SECRET')).update(id + '.' + timestamp).digest('hex');
    return {postData: {contents: JSON.stringify({application_id: id, timestamp, signature, ...overrides})}};
  };
  return {context, sent, properties, event, post: (input) => context.doPost(input), held: () => held};
}

test('signed events send only to owner; same ID never resends', () => {
  const h = harness();
  assert.equal(h.post(h.event()).ok, true);
  assert.equal(h.post(h.event()).ok, true);
  assert.equal(h.sent.length, 1);
  assert.equal(h.sent[0].to, 'gbob4549@gmail.com');
  assert.match(h.sent[0].body, /https:\/\/olist-revenueops.pages.dev\/pilot\/applications/);
  assert.equal(h.held(), false);
  h.context.authorizeNotifications();
  assert.equal(h.sent.length, 1, 'authorization helper sends nothing');
});

test('invalid, stale, future, missing and malformed requests send nothing', () => {
  const h = harness();
  for (const input of [null, {postData: {contents: '{'}}, {postData: {contents: 'x'.repeat(1025)}},
    h.event('a'.repeat(16), {signature: 'b'.repeat(64)}), h.event('a'.repeat(16), {timestamp: 1}),
    h.event('a'.repeat(16), {timestamp: Math.floor(Date.now() / 1000) + 600}),
    h.event('invalid-id'), h.event('a'.repeat(16), {timestamp: '1'})]) assert.equal(h.post(input).ok, false);
  assert.equal(h.sent.length, 0);
});

test('busy and exhausted quota send nothing; maximum 20 attempts per day', () => {
  for (const options of [{locked: true}, {quota: 0}]) {
    const h = harness(options);
    assert.equal(h.post(h.event()).ok, false);
    assert.equal(h.sent.length, 0);
  }
  const h = harness();
  for (let i = 0; i < 21; i++) assert.equal(h.post(h.event(i.toString(16).padStart(16, '0'))).ok, i < 20);
  assert.equal(h.sent.length, 20);
});

test('ambiguous send failure is never retried; lock released', () => {
  const h = harness({failSend: true});
  assert.equal(h.post(h.event()).ok, false);
  assert.equal(h.post(h.event()).ok, false);
  assert.equal(h.sent.length, 1);
  assert.equal(h.held(), false);
});

test('request cannot choose recipient/body; expired history pruned', () => {
  const h = harness();
  h.properties.set('notification_expired', 'sent:1');
  assert.equal(h.post(h.event('b'.repeat(16), {to: 'attacker@example.com', body: 'private data'})).ok, true);
  assert.equal(h.sent[0].to, 'gbob4549@gmail.com');
  assert.doesNotMatch(h.sent[0].body, /private data/);
  assert.equal(h.properties.has('notification_expired'), false);
});
