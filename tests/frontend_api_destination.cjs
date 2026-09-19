const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');

(async () => {
  const requests = [];
  const context = {
    URL,
    ctx: { api_base_url: 'https://attacker.invalid' },
    fetch: async (url, options) => { requests.push({ url, options }); return { ok: true }; },
  };
  vm.runInNewContext(fs.readFileSync('miniapp/api-config.js', 'utf8'), context);
  const api = context.MiniappApi;
  const initData = 'synthetic-auth-data';
  assert.equal(api.baseUrl, 'https://quiz-api.librechat.online');
  const forbidden = [
    'https://attacker.invalid/miniapp/setup',
    'https://quiz-api.librechat.online.attacker.invalid/miniapp/setup',
    'https://quiz-api.librechat.online@attacker.invalid/miniapp/setup',
    'https://user:password@quiz-api.librechat.online/miniapp/setup',
    'http://quiz-api.librechat.online/miniapp/setup',
    'https://quiz-api.librechat.online:444/miniapp/setup',
    'https://quiz-api.librechat.online/miniapp/../other',
    'javascript:alert(1)',
  ];
  for (const url of forbidden) {
    await assert.rejects(api.fetch(url, { body: initData, headers: { Authorization: initData } }));
  }
  assert.equal(requests.length, 0, 'Forbidden destinations must never reach fetch');
  await api.fetch(`${api.baseUrl}/miniapp/setup`, { method: 'POST', body: initData, redirect: 'follow' });
  assert.equal(requests[0].options.redirect, 'error');
  assert.equal(requests[0].options.body, initData);
  assert.equal(requests[0].url, `${api.baseUrl}/miniapp/setup`);
  assert(Object.isFrozen(api));
  const html = fs.readFileSync('miniapp/index.html', 'utf8');
  assert(!html.includes('ctx?.api_base_url'), 'URL context must not configure API credentials destination');
  assert(html.includes('window.MiniappApi.fetch(url,'), 'Every API call uses the verified fetch boundary');
  assert(!/\breturn await fetch\(/.test(html));
  console.log('Trusted API destination and redirect protection PASS');
})().catch(error => { console.error(error); process.exitCode = 1; });
