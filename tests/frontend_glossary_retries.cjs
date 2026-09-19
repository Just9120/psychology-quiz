const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');

(async () => {
  const html = fs.readFileSync('miniapp/index.html', 'utf8');
  const code = html.slice(html.indexOf('async function runGlossaryAction('), html.indexOf('function renderGlossaryState('));
  let resolve;
  let calls = 0;
  let rendered = 0;
  const context = {
    glossaryRenderRevision: 1,
    glossaryView: { hidden: false },
    runnerState: { textContent: '' },
    glossaryFetch: async () => { calls++; return new Promise(r => { resolve = r; }); },
  };
  vm.runInNewContext(code, context);
  const button = { disabled: false, isConnected: true, classList: { remove() {} } };
  const payload = { action: 'answer', session_id: 'synthetic', step_id: 1, selected_option_index: 2 };
  const apply = () => { rendered++; context.glossaryRenderRevision++; };
  const pending = context.runGlossaryAction(button, payload, apply);
  await context.runGlossaryAction(button, payload, apply);
  assert.equal(calls, 1, 'Double taps cannot create parallel UI actions');
  resolve({ resp: { ok: true }, data: { ok: true, glossary_state: {} } });
  await pending;
  assert.equal(rendered, 1);

  button.disabled = false;
  context.glossaryFetch = async () => { throw new Error('Lost response'); };
  await context.runGlossaryAction(button, payload, apply);
  assert.equal(button.disabled, false, 'Unconfirmed request can be retried');
  assert(context.runnerState.textContent.includes('Нет подтверждения'));
  context.glossaryFetch = async (_path, sent) => {
    assert.equal(sent, payload, 'Retry retains the exact step and selected answer');
    return { resp: { ok: true }, data: { ok: true, glossary_state: {} } };
  };
  await context.runGlossaryAction(button, payload, apply);
  assert.equal(rendered, 2);

  button.disabled = false;
  context.glossaryFetch = async () => new Promise(r => { resolve = r; });
  const stale = context.runGlossaryAction(button, payload, apply);
  context.glossaryRenderRevision++;
  resolve({ resp: { ok: true }, data: { ok: true, glossary_state: {} } });
  await stale;
  assert.equal(rendered, 2, 'Late reply cannot replace a newer question/view');
  assert(html.includes('step_id: q.step_id || q.order_index'));
  assert(html.includes('step_id: question.step_id || question.order_index'));
  console.log('Glossary lost response, double tap and stale UI response PASS');
})().catch(error => { console.error(error); process.exitCode = 1; });
