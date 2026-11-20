import { runScript } from './main.js';
import { createScriptServer } from '../../../internal_services/script-server.mjs';

const hostname = '127.0.0.1';
const port = 3020;
const server = createScriptServer(runScript, 'ANYHEDGE_JS_AUTH_TOKEN');

server.listen(port, hostname, () => {
  console.log(`Server running at http://${hostname}:${port}/`);
});
