# Nostr Last Online API

## Overview

Returns the latest known online timestamp for one or more Nostr pubkeys. The timestamp is the most recent of:

- `NostrPubkey.last_active` — updated when the pubkey registers or when the relay watcher detects an incoming message for it
- `Wallet.last_balance_check` — updated when a linked wallet polls the watchtower for its balance

## Endpoint

```
POST /api/nostr/last-online/
```

No authentication required.

## Request Body

```json
{
  "pubkeys": [
    "aabbccdd0011eeffaabbccdd0011eeffaabbccdd0011eeffaabbccdd0011eeff",
    "bbccddee0022ffaabbccddee0022ffaabbccddee0022ffaabbccddee0022ffaa"
  ]
}
```

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `pubkeys` | array of strings | Yes | 64-character hex-encoded Nostr public keys. Max 500 entries. |

## Response (200 OK)

```json
{
  "aabbccdd0011eeffaabbccdd0011eeffaabbccdd0011eeffaabbccdd0011eeff": "2026-06-28T12:34:56.789Z",
  "bbccddee0022ffaabbccddee0022ffaabbccddee0022ffaabbccddee0022ffaa": null
}
```

A flat JSON object mapping each requested pubkey to either:
- An ISO-8601 UTC timestamp string (e.g. `"2026-06-28T12:34:56.789Z"`) — the latest activity time
- `null` — no activity recorded for that pubkey

## Response (400 Bad Request)

Returned when the payload is missing, empty, contains invalid hex strings, or exceeds 500 entries.

```json
{
  "pubkeys": ["'not-hex' is not a valid 64-character hex string."]
}
```

## Client Usage Example

```javascript
const response = await fetch("https://your-host.com/api/nostr/last-online/", {
  method: "POST",
  headers: { "Content-Type": "application/json" },
  body: JSON.stringify({
    pubkeys: ["aabbccdd0011eeffaabbccdd0011eeffaabbccdd0011eeffaabbccdd0011eeff"]
  })
});

const data = await response.json();
const lastOnline = data["aabbccdd0011eeffaabbccdd0011eeffaabbccdd0011eeffaabbccdd0011eeff"];
// "2026-06-28T12:34:56.789Z" or null
```

## Notes

- A pubkey with `null` means watchtower has no record of any activity for it.
- The endpoint is publicly accessible (no auth) so chat UIs can display online indicators without requiring user tokens.
- If a pubkey maps to multiple wallet hashes, the most recent timestamp across all linked wallets is returned.
