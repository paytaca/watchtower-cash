import { createScriptServer as createAuthenticatedServer } from '../../../internal_services/script-server.mjs';

export function createScriptServer(runScript, environment = process.env) {
  return createAuthenticatedServer(runScript, 'STABLEHEDGE_JS_AUTH_TOKEN', environment);
}
