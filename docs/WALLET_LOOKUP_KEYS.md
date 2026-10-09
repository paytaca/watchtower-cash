# Wallet Lookup Keys

An opaque bearer key that maps to a `wallet_hash`, so a trusted backend can read
a wallet's balances without holding that wallet's auth token.

The intended caller is another Django server on our own infrastructure — not a
browser. CORS and CSRF are therefore not concerns.

## Model

`main.WalletLookupKey` — see `main/models.py`.

| Field | Notes |
|---|---|
| `key_hash` | HMAC-SHA256 digest, unique + indexed. The only thing stored. |
| `wallet` | `OneToOneField` → `Wallet`, cascade delete. Enforces one key per wallet. |
| `label` | Free-text, for operators to identify the key. |
| `date_created` | Auto-set. |
| `last_used_at` | Updated on each successful balance read. |

**There is no `is_active` column.** Revocation is a hard delete everywhere. A
soft-revoked row would occupy the one-to-one slot and permanently block that
wallet from ever minting a new key.

### Key handling

- Keys are **server-generated**: 40 chars from `get_random_string`, matching
  `Wallet.auth_token` entropy.
- Only `HMAC-SHA256(raw_key, LOOKUP_KEY_SECRET)` is persisted. The raw key is
  returned **exactly once**, in the `POST` response, and is unrecoverable
  afterwards.
- HMAC is keyed with `LOOKUP_KEY_SECRET`, so a database leak on its own is not
  enough to mount a lookup attack against the digests.

### Rotating the secrets

`LOOKUP_KEY_SECRET` is deliberately **not** `SECRET_KEY`. `SECRET_KEY` is also
Django's signing key for sessions and CSRF tokens, so rotating it is disruptive
in its own right — but if lookup keys were keyed with it, a routine rotation
would invalidate every issued key at once: each digest changes, every partner
integration starts returning `401`, and because only the digest is stored **the
raw keys cannot be recovered**. There is no dual-key acceptance path, so every
wallet owner would have to re-mint and re-distribute.

Rotating `LOOKUP_KEY_SECRET` does the same thing — deliberately, and only to the
lookup keys. That is the trade: a key you *can* rotate independently, instead of
one coupled to Django's.

Set it in the environment; it falls back to `SECRET_KEY` so nothing breaks if it
is absent. When it is absent, `settings.py` logs a warning at startup, because
the fallback re-couples the two and that should not be silent.

## Endpoints

### `POST /api/wallet/lookup-keys/` — mint

Auth: `wallet-hash` header **plus** `Authorization: Token <token>`.

Requires a valid Fernet token, not just a wallet hash. Anyone who knows a wallet
hash must not be able to mint a credential for it.

```bash
curl -X POST https://watchtower.cash/api/wallet/lookup-keys/ \
  -H 'wallet-hash: <wallet_hash>' \
  -H 'Authorization: Token <auth_token>' \
  -H 'Content-Type: application/json' \
  -d '{"label": "partner-server"}'
```

`201`:
```json
{
  "id": 1,
  "lookup_key": "Xy9...raw key, shown once...",
  "label": "partner-server",
  "date_created": "2026-10-08T12:00:00Z"
}
```

`409` if the wallet already has a key. The existing key keeps working.

The existence check runs **before** body validation, so a wallet that already has
a key gets `409` even when the body would have been rejected. That ordering is
deliberate — it is what guarantees a malformed request cannot disturb a live key.
A caller who hits it will get the real validation error on a retry after
revoking. In practice the invalid surface is small, since `label` is the only
input field.

The request body accepts **`label` only**. There is no `wallet` field: the key is
always bound to the wallet authenticated by the `wallet-hash` + `Authorization`
headers, so a caller cannot bind a key to somebody else's wallet by sending one.
Any `wallet` value in the body is ignored.

### `GET /api/wallet/lookup-keys/balances/` — read

Auth: `X-Api-Key` header.

The **BCH balance is always returned** in the top-level `bch` field on every
request. It is not an asset id and never needs to be requested — `assets` only
adds CashTokens on top of it.

| Param | Required | Description |
|---|---|---|
| `assets` | no | Comma-separated CashToken ids. Omit for BCH only. Max 20. |

Accepted asset ids:

| Id | Meaning |
|---|---|
| `ct/<category>` | CashToken fungible balance |
| `ct/<category>/<txid>/<index>` | CashToken NFT — `1` if held, else `0` |

Passing `bch` is rejected with a `400` rather than silently ignored.

```bash
curl 'https://watchtower.cash/api/wallet/lookup-keys/balances/?assets=ct/9f2a...c4,ct/1e8b...07' \
  -H 'X-Api-Key: <lookup_key>'
```

`200`:
```json
{
  "wallet_hash": "...",
  "bch": { "balance": 1.23456789, "spendable": 1.23456789, "valid": true },
  "assets": [
    {
      "asset_id": "ct/9f2a...c4",
      "balance": 100.5,
      "decimals": 2,
      "found": true,
      "name": "My Token",
      "symbol": "MTK"
    }
  ]
}
```

Status codes:

| Code | When |
|---|---|
| `200` | Success |
| `400` | Malformed asset id, an `slp/...` id, or `bch` |
| `401` | Missing, unknown, or revoked `X-Api-Key` |

All failures return `401` with `WWW-Authenticate: X-Api-Key` — including a
completely missing header. `LookupKeyAuthentication` raises rather than
returning `None` in that case on purpose: it is the only authenticator on the
view, so returning `None` would leave `request.user` as `AnonymousUser` and push
the failure into the handler, turning a missing header into a `500`.
`IsAuthenticatedLookupKey` backs this up as a second line of defence.

**Unknown assets are not errors.** A category that does not exist in our database
returns `balance: 0, found: false` so one bad id in a batch does not fail the
whole read.

### `DELETE /api/wallet/lookup-keys/` — revoke

Same auth as `POST`. Hard-deletes the wallet's key.

- `204` on success
- `404` if the wallet has no key

Clears the wallet's cached balances so the next read is fresh.

## SLP is not supported

SLP exists only for backwards compatibility. Sending `slp/...` returns `400`
with an explicit message rather than a silent zero balance.

Note that **BCH balance is wallet_type-agnostic** — it filters on
`token.name == 'bch'`, so wallets of type `slp` or `sbch` still get a correct BCH
balance in the `bch` field. They simply cannot request token balances.

## Rotation is two calls

Because only the digest is stored, the raw key is unrecoverable the moment it is
lost, and `POST` returns `409` when a key already exists. So you **cannot**
rotate by re-posting. Mint a new key with:

1. `DELETE /api/wallet/lookup-keys/`
2. `POST /api/wallet/lookup-keys/`

`DELETE` returns `404` when no key exists, so this sequence is safe to retry.

> **Consequence:** if the caller loses its key it cannot recover on its own. The
> only routes back are an admin delete or the `revoke_lookup_key` management
> command. Do not build a "just re-POST to rotate" assumption into the caller.

## Revoking someone else's key

For wallets whose owner has lost access and can no longer revoke their own key.

### Django admin

Django's `ModelAdmin` grants delete by default, so registering the model gives
admins a delete button on the changelist and detail page, plus bulk *delete
selected*. The practical handle is the wallet hash — search on it:

```
/admin/main/walletlookupkey/?q=<wallet_hash>
```

Admins cannot search by the raw key, since only its digest is stored.

### Management command

For bulk or incident response, where the admin UI is impractical.

```bash
python manage.py revoke_lookup_key <wallet_hash> [<wallet_hash> ...]
python manage.py revoke_lookup_key <wallet_hash> --dry-run
```

Reports `no lookup key` for wallets that have none. `--dry-run` prints what
would be revoked without deleting.

## Rate limiting

Two separate scopes, configured via `DEFAULT_THROTTLE_RATES` in
`watchtower/settings.py`:

| Scope | Throttle | Rate | Covers |
|---|---|---|---|
| `wallet_lookup_key` | `WalletLookupKeyThrottle` | `600/min` | `GET .../balances/` — a server-to-server partner polling on a schedule |
| `wallet_lookup_key_manage` | `WalletLookupKeyManageThrottle` | `60/min` | `POST` / `DELETE` — a human clicking a button |

They are deliberately separate buckets. With a shared scope and IP-keying, a
partner server polling at the read limit could throttle a user trying to revoke
their own key — on exactly the lockout path that admin-side revocation exists to
solve.

**Bucket identity differs by scope:**

- **Reads are keyed by lookup key** (`key{pk}`), because DRF authenticates before
  `check_throttles()`, so `request.user` is already the resolved
  `WalletLookupKey` by then. Every partner sits behind nginx and therefore shares
  an egress IP, so IP-keying meant all partners shared one budget. Keying by
  lookup key gives each partner its own.
  Keyed by primary key rather than `key_hash` — the digest is credential-derived
  and has no business in a cache key that might be logged or dumped.
- **Mint/revoke remain IP-keyed.** These are wallet-authenticated and
  human-paced, so an IP bucket is the right granularity; a per-wallet bucket
  would let one compromised wallet's token mint without limit.

Two caveats worth knowing:

- **Not a brute-force control.** DRF runs authentication and permission checks
  *before* `check_throttles()`, so requests that fail auth are never metered —
  verified: unauthenticated and bad-key requests write no throttle keys at all.
  These limits bound *legitimate* traffic; they do nothing against credential
  guessing, which is not a practical threat against a 256-bit key anyway.
- **Mint/revoke still key on IP**, so behind nginx every user's wallet traffic
  shares that bucket. `60/min` is generous for a human clicking a button, but if
  the proxy's `X-Forwarded-For` handling ever changes, expect the bucket
  identity to shift.

## Implementation notes

- `main/utils/wallet_balances.py` holds the balance maths. Unlike
  `view_balance.Balance`, these functions are **side-effect free**: they do not
  write `wallet.last_balance_check` and never enqueue `rescan_utxos`.
- The aggregation primitives (`_get_bch_balance`, `_get_ct_balance`,
  `_get_slp_balance`) live in that module too — they used to be in
  `main/views/view_balance.py`, but `main/utils/` needed them and importing up
  into `views/` inverted the layering. `view_balance.py` re-exports them, so its
  behaviour is unchanged.
- **Uses its own Redis namespace** — `lookup:balance:*`, deliberately separate
  from the balance endpoint's `wallet:balance:*`.

  An earlier draft shared those keys on the theory that reads here would warm the
  other endpoint's cache. That does not work, because both readers replace their
  *entire* response with whatever they read back
  (`data = json.loads(cached_data)`) and the two endpoints want different
  payload shapes. Sharing meant a lookup read silently stripped `wallet`, `yield`,
  `spendable` and `token_id` from the balance endpoint's responses — and, in the
  other direction, stripped `decimals` and `found` from this one. Namespacing
  costs one extra aggregate query per endpoint per TTL window; the sharing was
  the liability, not the feature.

- **NFT cache entries are keyed by token identity**, not by category alone.
  `view_balance.Balance` keys by category, which makes every NFT in a category
  share one slot, so reading NFT #1 then NFT #2 returns NFT #1's balance. This
  endpoint keys NFTs as `lookup:balance:nft:{hash}:{category}:{txid}:{index}`,
  avoiding that. (The pre-existing collision in `view_balance.py` is untouched.)

- **Revoke invalidates only the affected wallet.** `clear_lookup_balance_cache()`
  in `main/utils/wallet_balances.py` is shared by the revoke endpoint and the
  `revoke_lookup_key` command so the glob cannot drift between them. `wallet_hash`
  is a free-form `CharField` with no format constraint, so a glob ending in a bare
  `*` would also match hashes that merely start with the same string —
  invalidating `wallet-hash-1` would sweep `wallet-hash-10`. The token glob is
  therefore anchored with a trailing `:`, and the BCH key is deleted explicitly
  because it is the only key with no segment after the hash and so a `:'-anchored
  pattern would silently miss it. Cache failures are swallowed: revocation must
  succeed even when Redis does not.
- **One aggregate query per asset**, capped at 20. Multi-token batching is
  unreliable on `psqlextra`'s `PostgresModel` manager; see the note on
  `_get_slp_balance` in `main/utils/wallet_balances.py` and
  [django-postgres-extra#143](https://github.com/SectorLabs/django-postgres-extra/issues/143).

## Tests

`main/tests.py`, 70 tests across 11 classes:

| Class | Covers |
|---|---|
| `TestParseAssetId` | Asset id grammar, incl. explicit SLP and `bch` rejection |
| `TestHashKey` | Digest determinism, uniqueness, raw key never stored, independence from `SECRET_KEY` |
| `TestWalletLookupKeyMint` | `201`, `409`, digest never returned, auth required, one-row-per-wallet, 409-before-validation precedence |
| `TestWalletLookupKeyRevoke` | `204`, `404`, ownership scoping, rotation |
| `TestWalletLookupKeyBalances` | Balance reads, `401`s, `400`s, `last_used_at`, revoked key, NFTs with and without BCMR metadata, NFT-only `commitment`/`capability`, schema/response field parity |
| `TestWalletLookupKeyAdmin` | Admin delete for a locked-out wallet |
| `TestRevokeLookupKeyCommand` | Bulk revoke, `--dry-run`, no-key reporting |
| `TestWalletLookupKeyCacheIsolation` | Cache namespace separation from the balance endpoint, and NFT key collisions |
| `TestLookupBalanceCacheInvalidation` | Revoke-time cache invalidation: exact wallet only, no prefix collisions, survives Redis failure |
| `TestWalletLookupKeyRouting` | URL resolution for both routes, and unknown subpaths 404ing |
| `TestWalletLookupKeyThrottleScopes` | Mint/revoke and read use separate throttle buckets; read bucket is keyed per lookup key, not per IP |

`TestWalletLookupKeyRouting` needs no DB, so it runs even without Postgres.
It exists because both URL patterns were originally unanchored: `re_path` matches
with `re.search` semantics and discards the unconsumed remainder, so
`wallet/lookup-keys/` prefix-matched `wallet/lookup-keys/balances/` and, being
registered first, swallowed it. Balance requests landed on the mint view and
failed its wallet authentication with `403` rather than `404` — indistinguishable
from correct auth behaviour to a suite that only asserted `200`s and auth
failures. Both patterns are now anchored.

`TestWalletLookupKeyCacheIsolation` uses an in-memory `FakeRedis` rather than a
`MagicMock`, because a mock whose `get()` always returns `None` can never
exercise a cache *hit* — which is precisely the path where the two endpoints used
to collide.

Run with:

```bash
docker-compose run --rm test pytest main/tests.py -k LookupKey -v
```
