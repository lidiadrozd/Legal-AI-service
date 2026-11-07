const assert = require('node:assert/strict');
const { readFileSync } = require('node:fs');
const path = require('node:path');
const ts = require('typescript');
const { createRequire } = require('node:module');
const localRequire = createRequire(__filename);
const storage = () => {
  const values = new Map();
  return { getItem: key => values.get(key) ?? null,
    setItem: (key, value) => values.set(key, String(value)),
    removeItem: key => values.delete(key), clear: () => values.clear() };
};
global.localStorage = storage();
global.sessionStorage = storage();
const modules = new Map();
function load(file, mocks = {}) {
  const filename = path.resolve(__dirname, '../src', file);
  const output = ts.transpileModule(readFileSync(filename, 'utf8'), {
    compilerOptions: { module: ts.ModuleKind.CommonJS, jsx: ts.JsxEmit.ReactJSX },
  }).outputText;
  const compiled = { exports: {} };
  const requireModule = name => {
    if (Object.hasOwn(mocks, name)) return mocks[name];
    if (name.startsWith('@/')) {
      if (!modules.has(name)) modules.set(name, load(name.slice(2) + '.ts'));
      return modules.get(name);
    }
    return localRequire(name);
  };
  new Function('require', 'exports', 'module', output)(requireModule, compiled.exports, compiled);
  return compiled.exports;
}
localStorage.setItem('ai-lawyer-auth', JSON.stringify({ state: { accessToken: 'legacy-secret' } }));
const { useAuthStore } = load('store/authStore.ts');
assert.equal(localStorage.getItem('ai-lawyer-auth'), null);
modules.set('@/store/authStore', { useAuthStore });
const tokens = modules.get('@/utils/tokenStorage');
const user = { id: 1, email: 'test@example.org', is_consent_given: true };
useAuthStore.getState().setAuth(user, 'access', 'refresh', false);
assert.equal(sessionStorage.getItem('ai_lawyer_access_token'), 'access');
assert.equal(sessionStorage.getItem('ai_lawyer_refresh_token'), 'refresh');
assert.equal(localStorage.getItem('ai_lawyer_access_token'), null);
assert.equal(localStorage.getItem('ai_lawyer_refresh_token'), null);
assert.equal(localStorage.getItem('ai-lawyer-auth'), null);
sessionStorage.clear();
assert.equal(tokens.getAccessToken(), null);
assert.equal(tokens.getRefreshToken(), null);
useAuthStore.getState().setAuth(user, 'remembered', 'refresh2', true);
assert.equal(localStorage.getItem('ai_lawyer_access_token'), 'remembered');
useAuthStore.getState().logout();
assert.equal(tokens.getAccessToken(), null);
assert.equal(tokens.getRefreshToken(), null);
assert.equal(useAuthStore.getState().isAuthenticated, false);

// Exercise the actual App component and the session query it registers.
let query;
const AppRouter = () => null, CookieBanner = () => null, TermsUpdateBanner = () => null;
let meCalls = 0;
const mocks = {
  '@tanstack/react-query': { useQuery: options => { query = options; return { isPending: false, isError: false }; } },
  './router': { AppRouter },
  '@/components/common/CookieBanner': { CookieBanner },
  '@/components/common/TermsUpdateBanner': { TermsUpdateBanner },
  '@/api/auth': { authApi: { getMe: async () => { meCalls++; return user; } } },
};
const App = load('App.tsx', mocks).default;
const tree = App();
assert.ok(tree.props.children.some(child => child.type === TermsUpdateBanner));
assert.ok(query && typeof query.queryFn === 'function');
(async () => {
  await query.queryFn();
  assert.equal(meCalls, 0);
  tokens.setTokens('saved-access', 'saved-refresh', false);
  await query.queryFn();
  assert.equal(meCalls, 1);
  assert.equal(useAuthStore.getState().isAuthenticated, true);
  assert.equal(useAuthStore.getState().user.email, user.email);
  assert.equal(localStorage.getItem('ai_lawyer_access_token'), null);
  assert.equal(sessionStorage.getItem('ai_lawyer_access_token'), 'saved-access');
  assert.equal(localStorage.getItem('ai-lawyer-auth'), null);
  console.log('Auth storage, session restoration and terms banner checks passed');
})().catch(error => { console.error(error); process.exitCode = 1; });
