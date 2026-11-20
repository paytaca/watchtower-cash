import assert from 'node:assert/strict';
import http from 'node:http';
import { once } from 'node:events';
import { test } from 'node:test';
import { createScriptServer } from '../script-server.mjs';

const tokens = {
  STABLEHEDGE_JS_AUTH_TOKEN: 'stablehedge-synthetic-token-abcdefghijklmnopqrstuvwxyz-0123456789',
  ANYHEDGE_JS_AUTH_TOKEN: 'anyhedge-synthetic-token-abcdefghijklmnopqrstuvwxyz-0123456789',
};

async function request(server, authorization, body) {
  return new Promise((resolve, reject) => {
    const headers = authorization === undefined ? {} : { Authorization: authorization };
    const req = http.request({ hostname: '127.0.0.1', port: server.address().port, method: 'POST', headers }, res => {
      let content = '';
      res.setEncoding('utf8');
      res.on('data', chunk => { content += chunk; });
      res.on('end', () => resolve({ status: res.statusCode, content }));
      res.on('error', reject);
    });
    req.on('error', reject);
    req.end(body);
  });
}

for (const name of Object.keys(tokens)) {
  test(`${name}: invalid configuration prevents server creation`, () => {
    for (const token of [undefined, '', 'short', 'a'.repeat(64), 'a b'.repeat(30), tokens[name] + '\n']) {
      assert.throws(() => createScriptServer(() => {}, name, { [name]: token }), new RegExp(name));
    }
  });

  test(`${name}: only its own token may dispatch a script`, async () => {
    let calls = 0;
    const payload = { function: 'test', params: [{ wif: 'synthetic-private-key' }] };
    const server = createScriptServer(async data => {
      calls++;
      assert.deepEqual(data, payload);
      return { success: true, result: '{"signed":true}' };
    }, name, tokens);
    server.listen(0, '127.0.0.1');
    await once(server, 'listening');
    try {
      const other = Object.keys(tokens).find(key => key !== name);
      for (const authorization of [undefined, 'Bearer wrong', 'Bearer ' + tokens[name].slice(0, -1) + 'X', 'Bearer ' + tokens[other], 'Basic ' + tokens[name]]) {
        // An invalid body must not reach the JSON parser before authentication.
        const response = await request(server, authorization, '{invalid-secret-body');
        assert.deepEqual(response, { status: 401, content: 'Unauthorized' });
        assert.equal(calls, 0);
      }
      assert.deepEqual(await request(server, 'Bearer ' + tokens[name], JSON.stringify(payload)), {
        status: 200, content: '{"signed":true}',
      });
      assert.equal(calls, 1);
    } finally {
      await new Promise((resolve, reject) => server.close(error => error ? reject(error) : resolve()));
    }
  });
}
