import http from 'http';
import auth from './auth.cjs';

const MAX_REQUEST_BYTES = 1024 * 1024;

class RequestTooLargeError extends Error {
  constructor() {
    super('Request body too large');
    this.name = 'RequestTooLargeError';
  }
}

function readRequestData(req) {
  return new Promise((resolve, reject) => {
    let content = '';
    let size = 0;
    let settled = false;
    req.setEncoding('utf8');
    req.on('data', chunk => {
      if (settled) return;
      size += Buffer.byteLength(chunk, 'utf8');
      if (size > MAX_REQUEST_BYTES) {
        settled = true;
        reject(new RequestTooLargeError());
        return;
      }
      content += chunk;
    });
    req.on('end', () => { if (!settled) resolve(content); });
    req.on('error', error => { if (!settled) reject(error); });
    req.on('aborted', () => { if (!settled) reject(new Error('Request aborted')); });
  });
}

/**
 * Request bodies contain signing keys. Never log request data, headers, URLs,
 * script responses, or exception objects. Errors returned to Python callers
 * must also be safe to include in worker exception logs.
 */
export function createScriptServer(runScript, tokenName, environment = process.env) {
  const authenticate = auth.createServiceAuthenticator(tokenName, environment);
  return http.createServer(async (req, res) => {
    if (!authenticate(req, res)) return;
    try {
      const content = await readRequestData(req);
      let data;
      try {
        data = JSON.parse(content);
      } catch {
        res.writeHead(400, { 'Content-Type': 'text/plain' });
        res.end('Invalid JSON request');
        return;
      }

      const response = await runScript(data);
      if (!response?.success) {
        res.writeHead(400, { 'Content-Type': 'text/plain' });
        res.end('Script execution failed');
        return;
      }
      if (typeof response.result !== 'string') {
        throw new TypeError('Invalid script result');
      }
      res.writeHead(200, { 'Content-Type': 'application/json' });
      res.end(response.result);
    } catch (error) {
      if (error instanceof RequestTooLargeError) {
        if (!res.headersSent) {
          res.writeHead(413, { 'Content-Type': 'text/plain', Connection: 'close' });
        }
        res.end('Request body too large', () => req.destroy());
        return;
      }
      // Dependency errors can embed WIF values in their message or stack.
      console.error('Internal script request failed');
      if (!res.headersSent) {
        res.writeHead(500, { 'Content-Type': 'text/plain' });
      }
      res.end('Server Error');
    }
  });
}
