// Regression tests for extracted authentication and API modules.
const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');

let createApiClient, createAuthManager;
test.before(async () => {
  ({ createApiClient } = await import('../frontend/core/api.js'));
  ({ createAuthManager } = await import('../frontend/auth/auth-manager.js'));
});

test('concurrent initial auth checks share one request', async () => {
  let calls = 0;
  global.fetch = async () => {
    calls++;
    await new Promise(resolve => setTimeout(resolve, 5));
    return new Response(JSON.stringify({ username: 'operator', role: 'admin' }), { status: 200 });
  };
  const seenUsers = [];
  const auth = createAuthManager({ onUser: user => seenUsers.push(user) });
  const users = await Promise.all(Array.from({ length: 6 }, () => auth.requestAdminToken()));
  assert.equal(calls, 1);
  assert.equal(users.length, 6);
  assert.equal(seenUsers.length, 1);
});

test('API retries once after auth bootstrap and uses the HttpOnly session', async () => {
  const requests = [];
  let authCalls = 0;
  global.fetch = async (url, options = {}) => {
    requests.push({ url, options });
    if (url === '/api/private' && requests.filter(item => item.url === url).length === 1) {
      return new Response(JSON.stringify({ detail: 'unauthorized' }), { status: 401 });
    }
    return new Response(JSON.stringify({ ok: true }), { status: 200 });
  };
  const client = createApiClient({
    getToken: () => '', clearTokenIf: () => {},
    requestAdminToken: async () => { authCalls++; }
  });
  assert.deepEqual(await client.api('/api/private'), { ok: true });
  assert.equal(authCalls, 1);
  assert.equal(requests.filter(item => item.url === '/api/private').length, 2);
  assert.equal(requests[1].options.credentials, 'same-origin');
});

test('legacy browser token storage is not used and login UI is isolated', () => {
  const app = fs.readFileSync(require.resolve('../frontend/app.js'), 'utf8');
  const auth = fs.readFileSync(require.resolve('../frontend/auth/auth-manager.js'), 'utf8');
  assert.match(app, /createAuthManager/);
  assert.match(auth, /\/api\/auth\/me/);
  assert.match(auth, /\/api\/auth\/login/);
  assert.doesNotMatch(app + auth, /sessionStorage\.setItem\(\s*["']khoai-admin-token/);
  assert.match(auth, /name="username"/);
  assert.match(auth, /name="password"/);
});

test('POST helper sends JSON and same-origin credentials', async () => {
  const requests = [];
  global.fetch = async (url, options = {}) => {
    requests.push({ url, options });
    return new Response(JSON.stringify({ ok: true }), { status: 200 });
  };
  const client = createApiClient({ getToken: () => '', clearTokenIf: () => {}, requestAdminToken: async () => {} });
  assert.deepEqual(await client.post('/api/cards', { uid: 'AABBCCDD' }), { ok: true });
  const request = requests[0];
  assert.equal(request.options.method, 'POST');
  assert.equal(request.options.credentials, 'same-origin');
  assert.equal(new Headers(request.options.headers).get('Content-Type'), 'application/json');
  assert.deepEqual(JSON.parse(request.options.body), { uid: 'AABBCCDD' });
});
