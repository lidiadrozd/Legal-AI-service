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
const { startInterviewWithContextRecovery, isDocumentDraftIntent, shouldStartDocumentInterview } = load('../src/utils/documentInterview.ts');
const unavailable = { response: { status: 404, data: { error: { code: 'chat_context_unavailable', message: 'Чат недоступен' } } } };

(async () => {
  const payload = { prompt: 'После выезда не возвращён обеспечительный платёж 35000 рублей. Нужен иск.', chat_id: 20, filename: 'test', output_format: 'docx', title: 'Возврат платежа' };
  assert.deepEqual(await startInterviewWithContextRecovery(payload, async () => ({ chat_id: 20 })), { chat_id: 20 });
  for (const error of [
    { response: { status: 404, data: { error: 'Endpoint не найден' } } },
    { code: 'ETIMEDOUT' },
    { response: { status: 500, data: {} } },
    unavailable,
  ]) {
    let count = 0;
    await assert.rejects(startInterviewWithContextRecovery(payload, async () => { count++; throw error; }), e => e === error);
    assert.equal(count, 1);
  }
  let count = 0;
  await assert.rejects(startInterviewWithContextRecovery(payload, async () => { count++; throw unavailable; }), e => e === unavailable);
  assert.equal(count, 1); // Losing context must never create a fresh chat.
  assert.equal(payload.chat_id, 20);
  count = 0;
  await assert.rejects(startInterviewWithContextRecovery({ prompt: payload.prompt, output_format: 'docx' }, async () => { count++; throw unavailable; }), e => e === unavailable);
  assert.equal(count, 1);
  const { getApiErrorMessage } = load('../src/utils/apiError.ts', () => ({ default: { isAxiosError: () => true } }));
  assert.equal(getApiErrorMessage(unavailable, 'fallback'), 'Чат недоступен');
  const drafts = [
    'Составь иск', 'Составь претензию', 'Нужен иск.', 'Мне нужна претензия',
    'Подготовьте исковое заявление', 'Помоги мне составить претензию',
    'Можешь составить иск?', 'Пожалуйста, напиши трудовой договор',
    'Хочу составить иск', 'Нужно составить претензию', 'Хочу новую претензию',
    'иск', 'Претензия', 'трудовой договор', 'апелляционная жалоба',
    'Подготовь претензию. Я оплатил заказ, но продавец нарушил срок доставки и отказывается вернуть уплаченную сумму.',
    'Я передал деньги по договору. Должник не вернул их, хотя срок закончился и я неоднократно обращался к нему. Составь иск о взыскании долга.',
    'Не нужна претензия, а составь иск.',
    'Можно ли подать иск? Составь иск',
  ];
  const consultations = [
    'Что такое претензия?', 'Как расторгнуть договор?', 'Помоги проверить договор',
    'Как составить иск?', 'Какие данные нужны для иска?', 'Нужно ли составлять претензию?',
    'Что нужно для иска?', 'Хочу проверить договор', 'Договор уже подписан',
    'Я уже составил претензию', 'Не составляй претензию', 'Не нужен иск',
    'Не надо составлять претензию', 'Расскажи о претензии', 'актуальность закона',
    'Сделай расчёт по договору', 'Я хочу вернуть деньги по договору', 'Нужен совет по претензии',
    'Нужно проверить договор', 'Хочу, чтобы ответили на претензию', 'Я уже составил иск',
    'Составь ответ на иск', 'Подготовь возражения на иск', '',
  ];
  for (const text of drafts) assert.equal(isDocumentDraftIntent(text), true, text);
  for (const text of consultations) assert.equal(isDocumentDraftIntent(text), false, text);
  for (const phase of ['collecting', 'classifying', 'review_required']) {
    assert.equal(shouldStartDocumentInterview('Составь новый иск', { phase, scenario: 'pretense_debt_loan' }), false);
    for (const text of ['Другой случай: составь претензию', 'Теперь другой   случай: составь претензию', 'Пожалуйста, составь претензию по другому   делу']) {
      assert.equal(shouldStartDocumentInterview(text, { phase, scenario: 'pretense_debt_loan' }), true, `${phase}: ${text}`);
    }
    for (const text of ['Это не другое дело. Составь претензию', 'Составь претензию не по другому делу']) {
      assert.equal(shouldStartDocumentInterview(text, { phase, scenario: 'pretense_debt_loan' }), false, `${phase}: ${text}`);
    }
  }
  assert.equal(shouldStartDocumentInterview('Составь иск', { phase: 'ready', scenario: 'pretense_debt_loan' }), true);
  assert.equal(shouldStartDocumentInterview('Составь претензию', { phase: 'ready', scenario: 'claim_debt_loan' }), true);
  assert.equal(shouldStartDocumentInterview('Составь иск по договору', { phase: 'ready', scenario: 'claim_debt_loan' }), false);
  assert.equal(shouldStartDocumentInterview('Составь новый иск', { phase: 'ready', scenario: 'claim_debt_loan' }), true);
  assert.equal(shouldStartDocumentInterview('Подготовь иск', { phase: 'cancelled', scenario: 'claim_debt_loan' }), true);
  assert.equal(shouldStartDocumentInterview('Что такое претензия?', { phase: 'ready', scenario: 'claim_debt_loan' }), false);
  const completedPretense = { phase: 'ready', scenario: 'pretense_debt_loan' };
  for (const text of ['Теперь другой случай: составь претензию', 'Это другое дело. Составь претензию', 'Составь претензию по другому делу']) {
    assert.equal(shouldStartDocumentInterview(text, completedPretense), true, text);
  }
  for (const text of ['Это не другое дело. Составь претензию', 'Составь претензию не по другому делу']) {
    assert.equal(shouldStartDocumentInterview(text, completedPretense), false, text);
  }
  console.log('Interview routing, same-chat context, and retry checks passed');
})().catch(error => { console.error(error); process.exitCode = 1; });
