import assert from 'node:assert/strict';
import http from 'node:http';
import { once } from 'node:events';
import { createRequire } from 'node:module';
import { test } from 'node:test';
import auth from '../auth.cjs';

// Use the application's Express dependency, without loading wallet/network code.
const require = createRequire(new URL('../../multisig/js/server.js', import.meta.url));
const express = require('express');
const tokens = {
  ADDRESS_JS_AUTH_TOKEN: 'address-synthetic-token-abcdefghijklmnopqrstuvwxyz-0123456789',
  CTS_JS_AUTH_TOKEN: 'cts-synthetic-token-abcdefghijklmnopqrstuvwxyz-0123456789',
  MULTISIG_JS_AUTH_TOKEN: 'multisig-synthetic-token-abcdefghijklmnopqrstuvwxyz-0123456789',
};

async function request(server, authorization, method, body) {
  return new Promise((resolve, reject) => {
    const headers = { 'Content-Type': 'application/json' };
    if (authorization !== undefined) headers.Authorization = authorization;
    const req = http.request({ hostname: '127.0.0.1', port: server.address().port, path: '/helper', method, headers }, res => {
      let content = '';
      res.setEncoding('utf8');
      res.on('data', chunk => { content += chunk; });
      res.on('end', () => resolve({ status: res.statusCode, content }));
    });
    req.on('error', reject);
    req.end(body);
  });
}

for (const name of Object.keys(tokens)) {
  test(`${name}: startup requires valid configuration`, () => {
    for (const value of [undefined, '', 'short', 'a'.repeat(70)]) {
      assert.throws(() => auth.serviceAuthMiddleware(name, { [name]: value }), new RegExp(name));
    }
  });

  test(`${name}: authenticates GET/POST before Express parses input or runs routes`, async () => {
    let calls = 0;
    const app = express();
    app.use(auth.serviceAuthMiddleware(name, tokens));
    app.use(express.json());
    app.all('/helper', (req, res) => { calls++; res.json({ ok: true, body: req.body }); });
    const server = app.listen(0, '127.0.0.1');
    await once(server, 'listening');
    try {
      assert.equal(server.address().address, '127.0.0.1');
      const other = Object.keys(tokens).find(key => key !== name);
      for (const token of [undefined, 'Bearer wrong', 'Bearer ' + tokens[other], 'Bearer ' + tokens[name].slice(0, -1) + 'X']) {
        assert.deepEqual(await request(server, token, 'POST', '{malformed'), { status: 401, content: 'Unauthorized' });
        assert.equal(calls, 0);
      }
      for (const method of ['GET', 'POST']) {
        const result = await request(server, 'Bearer ' + tokens[name], method, method === 'POST' ? '{"test":1}' : undefined);
        assert.equal(result.status, 200);
        assert.equal(JSON.parse(result.content).ok, true);
        if (method === 'POST') assert.deepEqual(JSON.parse(result.content).body, { test: 1 });
      }
      assert.equal(calls, 2);
    } finally {
      await new Promise((resolve, reject) => server.close(error => error ? reject(error) : resolve()));
    }
  });
}
