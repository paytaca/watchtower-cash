import assert from 'node:assert/strict';
import http from 'node:http';
import { once } from 'node:events';
import { test } from 'node:test';
import { createScriptServer } from '../src/http-server.js';

const authToken = 'synthetic-test-service-token-abcdefghijklmnopqrstuvwxyz-0123456789';
const secret = 'synthetic-private-key-do-not-log';
const payload = { function: 'schnorrSign', params: [{ wif: secret, message: 'test' }] };

async function exercise(runScript, body = JSON.stringify(payload)) {
  const logs = [];
  const original = { log: console.log, error: console.error };
  console.log = (...args) => logs.push(args);
  console.error = (...args) => logs.push(args);
  const server = createScriptServer(runScript, { STABLEHEDGE_JS_AUTH_TOKEN: authToken });
  try {
    server.listen(0, '127.0.0.1');
    await once(server, 'listening');
    const response = await new Promise((resolve, reject) => {
      const request = http.request({
        hostname: '127.0.0.1', port: server.address().port,
        method: 'POST', path: '/?token=' + secret,
        headers: { Authorization: 'Bearer ' + authToken, 'Content-Type': 'application/json' },
      }, res => {
        let text = '';
        res.setEncoding('utf8');
        res.on('data', chunk => { text += chunk; });
        res.on('end', () => resolve({ status: res.statusCode, body: text }));
        res.on('error', reject);
      });
      request.on('error', reject);
      request.end(body);
    });
    return { ...response, logs };
  } finally {
    console.log = original.log;
    console.error = original.error;
    if (server.listening) await new Promise((resolve, reject) => server.close(error => error ? reject(error) : resolve()));
  }
}

test('signing arguments and successful responses are preserved without request logging', async () => {
  const result = JSON.stringify({ success: true, signature: 'synthetic-signature' });
  const response = await exercise(async data => {
    assert.deepEqual(data, payload);
    return { success: true, result };
  });
  assert.equal(response.status, 200);
  assert.equal(response.body, result);
  assert.deepEqual(response.logs, []);
});

test('returned script errors cannot propagate private keys into Python exception logs', async () => {
  const response = await exercise(async () => ({ success: false, error: 'Invalid WIF: ' + secret }));
  assert.equal(response.status, 400);
  assert.equal(response.body, 'Script execution failed');
  assert.deepEqual(response.logs, []);
});

test('thrown errors expose neither their message, custom properties nor stack', async () => {
  const response = await exercise(async () => {
    const error = new Error('Invalid key ' + secret);
    error.request = payload;
    throw error;
  });
  assert.equal(response.status, 500);
  assert.equal(response.body, 'Server Error');
  assert.deepEqual(response.logs, [['Internal script request failed']]);
  assert.ok(!JSON.stringify(response).includes(secret));
});

test('malformed JSON is rejected without logging the raw body or parsing error', async () => {
  const response = await exercise(() => { assert.fail('must not dispatch malformed JSON'); }, '{"wif":"' + secret);
  assert.equal(response.status, 400);
  assert.equal(response.body, 'Invalid JSON request');
  assert.deepEqual(response.logs, []);
});

test('empty body is rejected without invoking a signing function', async () => {
  const response = await exercise(() => { assert.fail('must not dispatch empty body'); }, '');
  assert.equal(response.status, 400);
  assert.deepEqual(response.logs, []);
});

test('oversized request bodies are rejected without dispatching or logging', async () => {
  const response = await exercise(
    () => { assert.fail('must not dispatch oversized body'); },
    'x'.repeat(1024 * 1024 + 1),
  );
  assert.equal(response.status, 413);
  assert.equal(response.body, 'Request body too large');
  assert.deepEqual(response.logs, []);
});
