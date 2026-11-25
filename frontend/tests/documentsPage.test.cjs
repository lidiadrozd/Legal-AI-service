const { readFileSync } = require('node:fs');
const assert = require('node:assert/strict');
const ts = require('typescript');

const source = readFileSync(
  new URL('../src/pages/Documents/DocumentsPage.tsx', `file://${__filename.replaceAll('\\', '/')}`),
  'utf8',
);

// Selecting a chat supplies context to the API; it must not silently submit
// boilerplate as though it were the person's request.
assert.match(source, /const \[aiPrompt, setAiPrompt\] = useState\(''\);/);
assert.match(source, /setSelectedChatId\(chat\);/);
assert.doesNotMatch(source, /Подготовить документ по материалам выбранного чата/);

const tree = ts.createSourceFile('DocumentsPage.tsx', source, ts.ScriptTarget.Latest, true, ts.ScriptKind.TSX);
let handler;
function visit(node) {
  if (ts.isVariableDeclaration(node) && node.name.getText(tree) === 'handleGenerate') handler = node.initializer.getText(tree);
  ts.forEachChild(node, visit);
}
visit(tree);
assert.ok(handler, 'Generate handler exists');
const handlerCode = ts.transpileModule(`module.exports = ${handler}`, {
  compilerOptions: { target: ts.ScriptTarget.ES2020, module: ts.ModuleKind.CommonJS },
}).outputText;
const runHandler = new Function('context', 'module', `
  const { setIsGenerating, generateMode, setAiQuestions, aiPrompt, addToast, filename,
    outputFormat, aiTitle, aiDocType, selectedChatId, startAttempt, documentsApi,
    setShowGenerateModal, setAiPrompt, setAiDocType, setAiTitle, setSelectedChatId,
    queryClient, navigate, getApiErrorMessage } = context;
  ${handlerCode}
  return module.exports();
`);

(async () => {
  const calls = [];
  const toasts = [];
  const noop = () => {};
  let failing = true;
  const context = {
    generateMode: 'ai', aiPrompt: 'ис', filename: 'draft', outputFormat: 'docx',
    aiTitle: '', aiDocType: '', selectedChatId: '20', startAttempt: { current: null },
    setIsGenerating: noop, setAiQuestions: noop, addToast: (item) => toasts.push(item),
    setShowGenerateModal: noop, setAiPrompt: noop, setAiDocType: noop, setAiTitle: noop,
    setSelectedChatId: noop, queryClient: { invalidateQueries: noop }, navigate: noop,
    getApiErrorMessage: (_error, fallback) => fallback,
    documentsApi: { startInterview: async (payload) => {
      calls.push(payload);
      if (failing) throw Error('transient failure');
      return { chat_id: 20 };
    } },
  };
  await runHandler(context, { exports: {} });
  assert.equal(calls.length, 0);
  assert.match(toasts[0].message, /3 символа/);
  context.aiPrompt = 'иск';
  await runHandler(context, { exports: {} });
  await runHandler(context, { exports: {} });
  assert.equal(calls.length, 2);
  assert.equal(calls[0].prompt, 'иск');
  assert.equal(calls[0].chat_id, 20);
  assert.equal(calls[0].start_request_id, calls[1].start_request_id);
  context.filename = 'new-name';
  await runHandler(context, { exports: {} });
  assert.notEqual(calls[1].start_request_id, calls[2].start_request_id);
  failing = false;
  await runHandler(context, { exports: {} });
  assert.equal(calls[2].start_request_id, calls[3].start_request_id);
  assert.equal(context.startAttempt.current, null);
  await runHandler(context, { exports: {} });
  assert.notEqual(calls[3].start_request_id, calls[4].start_request_id);
  console.log('Documents page context, short request, and stable retry checks passed');
})().catch((error) => { console.error(error); process.exitCode = 1; });
