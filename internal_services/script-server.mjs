import http from 'http';
import auth from './auth.cjs';

function readRequestData(req) {
  return new Promise((resolve, reject) => {
    let content = '';
    req.setEncoding('utf8');
    req.on('data', chunk => { content += chunk; });
    req.on('end', () => resolve(content));
    req.on('error', reject);
    req.on('aborted', () => reject(new Error('Request aborted')));
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
      res.writeHead(200, { 'Content-Type': 'application/json' });
      res.end(response.result);
    } catch {
      // Dependency errors can embed WIF values in their message or stack.
      console.error('Internal script request failed');
      if (!res.headersSent) {
        res.writeHead(500, { 'Content-Type': 'text/plain' });
      }
      res.end('Server Error');
    }
  });
}
