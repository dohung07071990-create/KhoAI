// Node.js built-in regression tests for the dashboard authentication bootstrap.
const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');

function loadAuth({initialToken = '', promptValue = 'valid-token'} = {}) {
  const store = new Map(initialToken ? [['khoai-admin-token', initialToken]] : []);
  let prompts = 0;
  const requests = [];
  const sessionStorage = {
    getItem: key => store.get(key) ?? null,
    setItem: (key, value) => store.set(key, String(value)),
    removeItem: key => store.delete(key),
  };
  const fakeFetch = async (url, options = {}) => {
    requests.push({url, options});
    const headers = new Headers(options.headers || {});
    const token = headers.get('X-Admin-Token');
    if (url === '/api/status') {
      return new Response(JSON.stringify({ok: true}), {status: token === 'valid-token' ? 200 : 401});
    }
    return new Response(JSON.stringify({ok: true}), {status: token === 'valid-token' ? 200 : 401});
  };
  const source = fs.readFileSync(require.resolve('../frontend/app.js'), 'utf8').split('// Tab')[0];
  const context = {
    sessionStorage, fetch: fakeFetch, Headers, Response,
    window: {prompt: () => { prompts++; return promptValue; }},
    document: {querySelector: () => null}, location: {href: 'http://localhost/'}, URL,
    console, setTimeout, clearTimeout,
  };
  vm.createContext(context);
  vm.runInContext(source + '\nglobalThis.testApi = api; globalThis.testPost = post;', context);
  return {api: context.testApi, post: context.testPost, requests, get prompts() { return prompts; }, store};
}

test('six simultaneous first-load requests share one prompt and all retry successfully', async () => {
  const app = loadAuth();
  const results = await Promise.allSettled(Array.from({length: 6}, (_, i) => app.api(`/api/test-${i}`)));
  assert.equal(app.prompts, 1);
  assert.equal(results.filter(x => x.status === 'fulfilled').length, 6);
  assert.equal(app.store.get('khoai-admin-token'), 'valid-token');
});

test('stale sessionStorage token is replaced once and concurrent requests succeed', async () => {
  const app = loadAuth({initialToken: 'old-token'});
  const results = await Promise.allSettled(Array.from({length: 6}, (_, i) => app.api(`/api/test-${i}`)));
  assert.equal(app.prompts, 1);
  assert.equal(results.filter(x => x.status === 'fulfilled').length, 6);
  assert.equal(app.store.get('khoai-admin-token'), 'valid-token');
});

test('cancelled prompt is suppressed and does not persist an empty token', async () => {
  const app = loadAuth({promptValue: ''});
  await assert.rejects(app.api('/api/test'));
  await assert.rejects(app.api('/api/test'));
  assert.equal(app.prompts, 1);
  assert.equal(app.store.has('khoai-admin-token'), false);
});


test('post helper exists and sends authenticated JSON', async () => {
  const app = loadAuth({initialToken: 'valid-token'});
  const result = await app.post('/api/cards', {uid: 'AABBCCDD'});
  assert.equal(result.ok, true);
  assert.equal(app.requests.length, 1);
  const request = app.requests[0];
  assert.equal(request.url, '/api/cards');
  assert.equal(request.options.method, 'POST');
  const headers = new Headers(request.options.headers || {});
  assert.equal(headers.get('Content-Type'), 'application/json');
  assert.equal(headers.get('X-Admin-Token'), 'valid-token');
  assert.deepEqual(JSON.parse(request.options.body), {uid: 'AABBCCDD'});
});
