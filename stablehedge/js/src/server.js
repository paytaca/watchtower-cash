import { runScript } from './main.js';
import { createScriptServer } from './http-server.js';

const hostname = '127.0.0.1';
const port = 3010;
const server = createScriptServer(runScript);

server.listen(port, hostname, () => {
  console.log(`Server running at http://${hostname}:${port}/`);
});
