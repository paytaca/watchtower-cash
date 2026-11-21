# Deployment changes — security patch

This document lists the deployment changes required by the current
`fix/security-patch` branch. It complements
[`CONTAINER_RUNTIME.md`](CONTAINER_RUNTIME.md), which covers the container
layout in more detail.

There are **no database migrations** in this patch. Existing sessions and JWTs
will be invalidated by the signing-key change.

## 1. Required secrets

Configure independent, randomly generated values for:

```bash
python -c "import secrets; print(secrets.token_urlsafe(64))"
```

| Variable | Requirement |
|---|---|
| `SECRET_KEY` | Django signing key; required, must not be the previously published key |
| `JWT_SIGNING_KEY` | SimpleJWT signing key; required and independent of `SECRET_KEY` |
| `LOOKUP_KEY_SECRET` | Preserve the existing independent value; do not rotate casually |
| `ADDRESS_JS_AUTH_TOKEN` | Shared by the address service and Python callers |
| `CTS_JS_AUTH_TOKEN` | Shared by the CTS service and Python callers |
| `MULTISIG_JS_AUTH_TOKEN` | Shared by the multisig service and Python callers |
| `ANYHEDGE_JS_AUTH_TOKEN` | Shared by the Anyhedge service and Python callers |
| `STABLEHEDGE_JS_AUTH_TOKEN` | Shared by the Stablehedge service and Python callers |

The five JavaScript service tokens must be independently generated. The same
value must be present in the corresponding Node process and in every Python
web/worker process that calls it.

Missing, blank, short, or repeated-character signing keys prevent Django from
starting. Changing `SECRET_KEY`/`JWT_SIGNING_KEY` invalidates existing sessions
and JWTs, so plan a coordinated rollout.

### Historical values that must be rotated

Blanking a template does not revoke a secret. Treat every value that ever
appeared in `.env_template` history as compromised, including the values below.
The commented Telegram literal that previously lived in `watchtower/settings.py`
has also been removed, but it remains in git history.

| Value | Required action |
|---|---|
| `SECRET_KEY` | Rotate. The previously published Django literal is denylisted by `watchtower/signing_secrets.py`. |
| `JWT_SIGNING_KEY` | Rotate. Never reuse the old Django key. |
| `TELEGRAM_BOT_TOKEN` | Revoke/regenerate the bot token; both the old template and the removed `settings.py` literal exposed it. |
| `SLACK_BOT_USER_TOKEN` | Revoke/regenerate the Slack bot token. |
| `SLACK_VERIFICATION_TOKEN` | Revoke/regenerate in the Slack app. |
| `SLACK_CLIENT_SECRET` | Regenerate the Slack app client secret. |
| `SLACK_SIGNING_SECRET` | Regenerate the Slack app signing secret. |
| `ANYHEDGE_SETTLEMENT_SERVICE_AUTH_TOKEN` | Rotate with the settlement service; update both sides together. |
| `SIDESHIFT_SECRET_KEY` | Regenerate the Sideshift secret. |
| `STABLEHEDGE_FERNET_KEY` | Rotate and re-encrypt stored values, or run a documented dual-key transition. |
| `STABLEHEDGE_AUTH_KEY_WALLET_WIF` | Replace the auth key and move any remaining funds from the old key. |

Rotate these values even if the repository history is rewritten or the
repository is private. Removing the literals from the current tree is not a
substitute for revocation.

## 2. Container identity and host paths

The application image runs as **UID/GID 10001** (`watchtower`). Supervisor and
Celery Beat write runtime files under:

- `/run/watchtower` — PID, socket, child logs, Celery Beat PID
- `/var/lib/watchtower` — Celery Beat schedule

Provision these host paths:

| Host path | Container path | Required access |
|---|---|---|
| `/var/opt/watchtower/credentials` | `/run/watchtower-credentials` | UID/GID 10001 read |
| `/var/www/images` | `/images` | UID/GID 10001 write |
| `/var/opt/watchtower/media` | `/code/media` | UID/GID 10001 write |
| `/var/opt/watchtower/private-p2p-proofs` | `/code/private-p2p-proofs` | UID/GID 10001 write |

Example:

```bash
install -d -o 10001 -g 10001 -m 0750 /var/opt/watchtower/credentials
install -d -o 10001 -g 10001 -m 0755 \
  /var/www/images \
  /var/opt/watchtower/media \
  /var/opt/watchtower/private-p2p-proofs
```

If you use existing Docker named volumes created before the non-root change,
verify their ownership and recreate or `chown` them for UID/GID 10001 before
starting the new container.

## 3. Runtime credentials

The credentials directory is mounted read-only at
`/run/watchtower-credentials`. It must contain:

- `firebase-admin-credentials.json`
- `APNS_AuthKey.p8` when APNs token authentication is enabled

Keep the local copies in `compose/credentials/<network>/`; `fab <network>
provision` mirrors that folder into `/var/opt/watchtower/credentials` with the
required ownership. Both folders are gitignored.

`compose/mainnet.yml` and `compose/chipnet.yml` set the Firebase path and
default the APNs path to:

```text
/run/watchtower-credentials/APNS_AuthKey.p8
```

Override `APNS_AUTH_KEY_PATH` only if the APNs key has a different filename.
Existing deployment env files may still contain the old
`compose/APNS_AuthKey.p8` value; the Compose `environment` block takes
precedence, but verify the resolved value with `docker compose config`.
The build context excludes `*.p8`, service-account JSON, env files, private
keys, uploads, and audit notes; credentials must be supplied at runtime.

## 4. Build and recreate

Build a fresh image and recreate the web/worker container together. Do not mix
old and new images across the web process, WebSocket process, and workers.

```bash
docker compose -f compose/<network>.yml --env-file compose/.env_<network> build --pull
docker compose -f compose/<network>.yml --env-file compose/.env_<network> \
  up -d --force-recreate
```

Before recreating, review queued Celery tasks:

- `rampp2p.tasks.task_contract.execute_subprocess`
- `rampp2p.tasks.task_transaction.execute_subprocess`

These generic tasks were removed. Any queued tasks referencing them will fail
and should be cleared or reviewed before the new workers consume them.

## 5. Cache format change

Wallet and POS history caches now use versioned JSON keys (`:json-v1`) instead
of pickle. Legacy pickle entries are ignored, not deserialized. No migration is
required; expect a cold cache after rollout. Old entries expire naturally.

## 6. Caller and behavior changes

### Stablehedge test utility

`POST /api/stablehedge/test-utils/price_message/` is now **POST-only**. A WIF
must be sent in the request body; it is no longer accepted in the query string
because URLs are captured by proxy/web-server access logs.

Update any scripts or clients that used:

```text
GET .../price_message/?wif=...
```

to send a POST body instead.

### Internal JavaScript services

All five internal Node services bind to `127.0.0.1` and require their bearer
token. `MULTISIG_JS_SERVER` must use loopback port `3004`; remote/custom
multisig destinations are no longer supported.

Anyhedge and Stablehedge no longer have a local `node` subprocess fallback. The
Supervisor-managed JS servers must be running; if they are unavailable, Python
callers raise `RuntimeError` instead of falling back to a subprocess.

### Payment and webhook destinations

Payment and webhook HTTP requests now:

- accept only public HTTP(S) destinations on standard ports (80/443)
- reject redirects
- reject private, loopback, link-local, multicast, and reserved destinations
- ignore environment HTTP proxies and `.netrc`
- cap responses at 1 MiB

Review existing webhook subscribers and payment providers for nonstandard ports
or redirects before rollout. Unsafe stored webhook destinations fail closed and
are marked invalid on delivery.

### Gift hostname

Apply the updated `compose/nginx.conf`. `gifts.paytaca.com` is restricted to
gift/claim routes, platform association files, and static assets; other Django
and WebSocket APIs return 404 on that hostname.

## 7. Post-deployment checks

1. Verify all web/worker processes start with the new signing keys and service
   tokens.
2. Confirm the container UID/GID is 10001 and that `/run/watchtower` and
   `/var/lib/watchtower` are writable.
3. Verify credential files are readable and APNs/Firebase initialization
   succeeds when enabled.
4. Smoke-test wallet/POS history, payment requests, webhooks, gifts,
   authentication, address utilities, CTS, multisig, Anyhedge, Stablehedge,
   P2P contract generation, uploads, notifications, workers, and scheduled jobs.
5. Build and run the opt-in container checks:

   ```bash
   RUN_CONTAINER_RUNTIME_TESTS=1 python -m unittest tests.test_container_runtime -v
   RUN_BUILT_IMAGE_RUNTIME_TESTS=1 \
   WATCHTOWER_TEST_IMAGE=watchtower_web:latest \
   python -m unittest tests.test_container_runtime -v
   ```
