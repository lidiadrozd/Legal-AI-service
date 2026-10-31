const { readFileSync } = require('node:fs');
const assert = require('node:assert/strict');
const ts = require('typescript');
function load(file, requireMock) {
  const source = readFileSync(new URL(file, `file://${__filename.replaceAll('\\', '/')}`), 'utf8');
  const output = ts.transpileModule(source, { compilerOptions: { module: ts.ModuleKind.CommonJS } }).outputText;
  const compiled = { exports: {} };
  new Function('exports', 'module', 'require', output)(compiled.exports, compiled, requireMock);
  return compiled.exports;
}
const { startInterviewWithContextRecovery } = load('../src/utils/documentInterview.ts');
const unavailable = { response: { status: 404, data: { error: { code: 'chat_context_unavailable', message: 'Чат недоступен' } } } };

(async () => {
  const payload = { prompt: 'После выезда не возвращён обеспечительный платёж 35000 рублей. Нужен иск.', chat_id: 20, filename: 'test', output_format: 'docx', title: 'Возврат платежа' };
  const calls = [];
  const result = await startInterviewWithContextRecovery(payload, async request => {
    calls.push(request);
    if (calls.length === 1) throw unavailable;
    return { chat_id: 101 };
  });
  assert.deepEqual(result, { chat_id: 101, context_omitted: true });
  assert.equal(calls.length, 2);
  assert.deepEqual(calls[1], { prompt: payload.prompt, filename: 'test', output_format: 'docx', title: 'Возврат платежа' });
  assert.equal(payload.chat_id, 20); // The caller's draft remains intact.
  assert.deepEqual(await startInterviewWithContextRecovery(payload, async () => ({ chat_id: 102 })), { chat_id: 102 });
  for (const error of [
    { response: { status: 404, data: { error: 'Endpoint не найден' } } },
    { code: 'ETIMEDOUT' },
    { response: { status: 500, data: {} } },
  ]) {
    let count = 0;
    await assert.rejects(startInterviewWithContextRecovery(payload, async () => { count++; throw error; }), e => e === error);
    assert.equal(count, 1);
  }
  let count = 0;
  await assert.rejects(startInterviewWithContextRecovery(payload, async () => { count++; throw unavailable; }), e => e === unavailable);
  assert.equal(count, 2); // Exactly one recovery attempt.
  count = 0;
  await assert.rejects(startInterviewWithContextRecovery({ prompt: payload.prompt, output_format: 'docx' }, async () => { count++; throw unavailable; }), e => e === unavailable);
  assert.equal(count, 1);
  const { getApiErrorMessage } = load('../src/utils/apiError.ts', () => ({ default: { isAxiosError: () => true } }));
  assert.equal(getApiErrorMessage(unavailable, 'fallback'), 'Чат недоступен');
  console.log('8 interview context recovery checks passed');
})().catch(error => { console.error(error); process.exitCode = 1; });
