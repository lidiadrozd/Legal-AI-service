const { readFileSync } = require('node:fs');
const assert = require('node:assert/strict');

const source = readFileSync(
  new URL('../src/pages/Documents/DocumentsPage.tsx', `file://${__filename.replaceAll('\\', '/')}`),
  'utf8',
);

// Selecting a chat supplies context to the API; it must not silently submit
// boilerplate as though it were the person's request.
assert.match(source, /const \[aiPrompt, setAiPrompt\] = useState\(''\);/);
assert.match(source, /setSelectedChatId\(chat\);/);
assert.doesNotMatch(source, /Подготовить документ по материалам выбранного чата/);

console.log('3 documents page prompt checks passed');
