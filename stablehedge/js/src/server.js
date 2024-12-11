import { runScript } from './main.js';
import http from 'http'
const hostname = '127.0.0.1';
const port = 3010;

/**
 * @param {http.IncomingMessage} req
 */
function readRequestData(req) {
  return new Promise((resolve, reject) => {
    let content = undefined

    req.on('data', (chunk) => {
      if (Buffer.isBuffer(chunk)) {
        chunk = chunk.toString('utf8');
      }
      if (content == undefined) content = ''
      content += chunk;
    });

    req.on('end', () => resolve(content))
  })
}

const server = http.createServer(async (req, res) => {
  const parsedRequest = {
    method: req.method,
    url: req.url,
    headers: req.headers,
    content: await readRequestData(req),
    _request: req,
  }
  Object.defineProperty(parsedRequest,'_request',{enumerable:false});

  try {
    parsedRequest.data = JSON.parse(parsedRequest.content)
    Object.defineProperty(parsedRequest,'data',{enumerable:false});
  } catch {}

  console.log(parsedRequest)

  try {
    const response = await requestHandler(parsedRequest)
    res.writeHead(response?.status, { 'Content-Type': 'application/json' });
    res.end(response?.content);
  } catch(error) {
    console.error(error)
    res.writeHead(500, { 'Content-Type': 'text/plain' });
    res.end('Server Error');
  }
});

/**
 * @param {Object} request 
 * @param {String} [request.method]
 * @param {String} [request.url]
 * @param {String} [request.content]
 * @param {Object} [request.data]
 * @param {http.IncomingHttpHeaders} request.headers
 * @param {http.IncomingMessage} request._request
 */
async function requestHandler(request) {
  const scriptResponse = await runScript(request.data)
  return {
    status: scriptResponse?.success ? 200 : 400,
    content: scriptResponse?.success ? scriptResponse?.result : scriptResponse?.error,
  }
}

server.listen(port, hostname, () => {
  console.log(`Server running at http://${hostname}:${port}/`);
});
