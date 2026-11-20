const { timingSafeEqual } = require('node:crypto');

function createServiceAuthenticator(name, environment = process.env) {
  const token = environment[name];
  if (typeof token !== 'string' || !/^[A-Za-z0-9_-]{43,}$/.test(token) || token !== token.trim() || new Set(token).size < 5) {
    throw new Error(`${name} must be set to a randomly generated URL-safe token of at least 43 characters`);
  }
  const expected = Buffer.from(`Bearer ${token}`, 'utf8');
  return function authenticate(req, res) {
    const header = req.headers.authorization;
    const supplied = Buffer.from(typeof header === 'string' ? header : '', 'utf8');
    if (supplied.length === expected.length && timingSafeEqual(supplied, expected)) return true;
    res.writeHead(401, { 'Content-Type': 'text/plain', 'WWW-Authenticate': 'Bearer' });
    res.end('Unauthorized');
    return false;
  };
}

module.exports = { createServiceAuthenticator };
