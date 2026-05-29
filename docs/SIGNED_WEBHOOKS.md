# Signed Webhooks

Watchtower can POST transaction notifications to an HTTP endpoint (webhook). When a **webhook secret** is registered for that endpoint, every outgoing request is signed with HMAC-SHA256 so the receiving server can verify the payload came from Watchtower and was not tampered with.

---

## How it works

### 1. Registration

Before subscribing addresses, the receiver registers its endpoint and chooses a secret:

```
POST /api/recipient/webhook-secret/
Content-Type: application/json

{
    "web_url": "https://example.com/webhook/",
    "webhook_secret": "<your-secret-min-32-chars>"
}
```

- Returns `201 Created` on success.
- Returns `409 Conflict` if a Recipient for that URL already exists.
- **First-one-wins**: only the first caller can claim a URL. This prevents an attacker from pre-registering your endpoint with a secret they control.
- The secret is stored encrypted at rest using Fernet symmetric encryption (see [At-rest encryption](#at-rest-encryption)).
- Rate limited to **10 requests / minute per IP**.

### 2. Subscribing addresses

Subscribe addresses as normal via `POST /api/subscribe/`. Pass `webhook_url` and optionally a `webhook_secret` (minimum 32 characters). If the URL already has a secret registered via the step above, the subscription will succeed only if the same secret is provided (or no secret is given and none was pre-registered).

If a different secret is detected for an existing URL that already has one, `WebhookOwnershipRequired` is raised and the subscription is rejected with `error: webhook_url_already_has_secret`.

### 3. Outgoing request format

When Watchtower fires a webhook it sends:

```
POST https://example.com/webhook/
Content-Type: application/json
X-Watchtower-Signature: sha256=<hex-digest>

{"address":"bitcoincash:q...","txid":"..."}
```

The body is a **canonicalised JSON** string — keys sorted alphabetically, no extra whitespace beyond Python's default `json.dumps` separators (`, ` and `: `). The same bytes that are in the body are what was signed.

---

## Verifying the signature

Always verify against the **raw request body** — do not re-parse and re-serialise, as that risks introducing encoding differences.

### Python (Django)

```python
import hashlib
import hmac
import json

WEBHOOK_SECRET = settings.WATCHTOWER_WEBHOOK_SECRET  # must match the registered secret

def verify_signature(request):
    sig_header = request.headers.get('X-Watchtower-Signature', '')
    if not sig_header.startswith('sha256='):
        return False
    expected = hmac.new(
        WEBHOOK_SECRET.encode('utf-8'),
        request.body,          # raw bytes — exactly what was signed
        hashlib.sha256,
    ).hexdigest()
    return hmac.compare_digest(f'sha256={expected}', sig_header)
```

### Python (Flask / generic WSGI)

```python
expected = hmac.new(
    WEBHOOK_SECRET.encode('utf-8'),
    request.get_data(),        # raw bytes
    hashlib.sha256,
).hexdigest()
return hmac.compare_digest(f'sha256={expected}', sig_header)
```

### Node.js

```js
const crypto = require('crypto');

function verifySignature(rawBody, sigHeader, secret) {
    const expected = 'sha256=' + crypto
        .createHmac('sha256', secret)
        .update(rawBody)   // Buffer of the raw request body
        .digest('hex');
    return crypto.timingSafeEqual(Buffer.from(expected), Buffer.from(sigHeader));
}
```

---

## Rotating the secret

```
PATCH /api/recipient/webhook-secret/
Content-Type: application/json

{
    "web_url": "https://example.com/webhook/",
    "current_webhook_secret": "<current-secret>",
    "new_webhook_secret": "<new-secret-min-32-chars>"
}
```

- Returns `200 OK` on success.
- Returns `403 Forbidden` if `current_webhook_secret` is wrong, or if no secret is set (use `POST` first).
- Returns `404 Not Found` if the URL has never been registered.
- Set `new_webhook_secret` to an empty string to **clear** the secret entirely (webhook will revert to unsigned form-encoded POSTs).
- Rate limited to **10 requests / minute per IP**.

---

## Unsigned (legacy) behaviour

Recipients without a `webhook_secret` continue to receive form-encoded `POST` requests with no signature header, preserving backward compatibility.

---

## At-rest encryption

Webhook secrets are **never stored in plaintext**. Watchtower encrypts them with Fernet (AES-128-CBC + HMAC-SHA256) before writing to the database, keyed by the `WEBHOOK_SECRET_KEY` environment variable.

### Required environment variable

```
WEBHOOK_SECRET_KEY=<Fernet key>
```

Generate a key:

```bash
python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
```

This must be set (and kept stable) on all Watchtower instances. Rotating this key requires re-encrypting all stored secrets.

---

## Security design notes

| Concern | Mitigation |
|---|---|
| Payload tampering | HMAC-SHA256 signature on every request |
| Replay attacks | (future) Add a timestamp/nonce claim to the payload |
| Secret leakage from DB | Fernet encryption at rest |
| Timing attacks on verification | `hmac.compare_digest()` on both sides |
| DDoS via subscription spam | `WebhookOwnershipRequired` blocks new recipients sharing a claimed URL |
| Brute-force secret guessing | Rate limit: 10 req/min per IP on the management endpoint |
| URL squatting | First-one-wins registration; challenge-response ownership proof is a planned future improvement |
