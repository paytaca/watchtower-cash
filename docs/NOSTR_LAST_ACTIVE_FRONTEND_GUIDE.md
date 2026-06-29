# Nostr Last-Active WebSocket & Touch Endpoint — Frontend Integration Guide

## Overview

Three new server-side pieces are available for real-time and cached "last active" (green dot) status:

| Resource | URL | Purpose |
|----------|-----|---------|
| **WebSocket** | `wss://watchtower.cash/ws/nostr/updates/<wallet_hash>/` | Receive real-time `last_active` events; send heartbeats so the server knows you're online |
| **Touch REST** | `POST /api/nostr/touch/` | Call immediately after sending a Nostr chat message so recipients see your green dot |
| **Query REST** | `POST /api/nostr/last-active/` | Batch-check cached timestamps for a list of pubkeys (chat list, profile pages, etc.) |

---

## 1. WebSocket — Connect & Heartbeat

### Connect

```javascript
const walletHash = '0a98ed0bbfef02789a6582fc78d4bb22233167f9f16688517ab42041246fc3a5';
const accessToken = '<bearer_token_from_oauth>';

// Pass token as query parameter (browser WebSockets can't set custom headers)
const wsUrl = `wss://watchtower.cash/ws/nostr/updates/${walletHash}/?token=${accessToken}`;

const ws = new WebSocket(wsUrl);

ws.onopen = () => {
  console.log('WS connected');
  // Start heartbeat
  startHeartbeat(ws);
};

ws.onmessage = (event) => {
  const msg = JSON.parse(event.data);
  // Expected shape:
  // {
  //   type: 'last_active',
  //   pubkey_hex: 'f9a70a99c295d3a0753bf92e365c83f33b03d7c50f7876f2b81cfbf2084d8660',
  //   timestamp: '2026-06-29T06:58:06.003828Z'
  // }
  handleLastActive(msg.pubkey_hex, msg.timestamp);
};

ws.onerror = (err) => console.error('WS error', err);
ws.onclose = () => {
  console.log('WS closed');
  stopHeartbeat();
  // Optionally reconnect with backoff
};
```

### Heartbeat

Send every **30 seconds** while the app is foregrounded. This updates your `last_active` on the server so other users polling the API see you as online.

```javascript
let heartbeatInterval;

function startHeartbeat(ws) {
  // Immediate first beat
  ws.send(JSON.stringify({ type: 'heartbeat' }));

  heartbeatInterval = setInterval(() => {
    if (ws.readyState === WebSocket.OPEN) {
      ws.send(JSON.stringify({ type: 'heartbeat' }));
    }
  }, 30_000); // 30s
}

function stopHeartbeat() {
  clearInterval(heartbeatInterval);
}
```

> **Important:** The server **rejects** any inbound message that is not exactly `{"type": "heartbeat"}` and will close the connection with code `4001`. Do not send anything else.

### Green Dot Logic

When you receive a `last_active` message, treat that pubkey as "online" for **3 minutes** (180s). After that, hide the green dot until a newer timestamp arrives or the next API poll refreshes it.

```javascript
const activeWindows = new Map(); // pubkey -> timeoutId

function handleLastActive(pubkeyHex, timestamp) {
  showGreenDot(pubkeyHex);

  // Clear previous timeout if any
  if (activeWindows.has(pubkeyHex)) {
    clearTimeout(activeWindows.get(pubkeyHex));
  }

  // Hide after 3 minutes
  const timeoutId = setTimeout(() => {
    hideGreenDot(pubkeyHex);
    activeWindows.delete(pubkeyHex);
  }, 180_000);

  activeWindows.set(pubkeyHex, timeoutId);
}
```

---

## 2. Touch Endpoint — Call After Sending a Message

Right after your client publishes a Nostr chat message, call this so each recipient gets a real-time `last_active` push on their WebSocket.

### Request

```javascript
async function touchAfterSend(senderPubkey, recipientPubkeys, accessToken) {
  const res = await fetch('https://watchtower.cash/api/nostr/touch/', {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      'Authorization': `Bearer ${accessToken}`,
    },
    body: JSON.stringify({
      pubkey: senderPubkey,
      recipients: recipientPubkeys, // e.g. ["b_pubkey_hex", "c_pubkey_hex"]
    }),
  });

  if (!res.ok) {
    const err = await res.json();
    console.error('Touch failed:', err);
    return;
  }

  return await res.json(); // { "status": "ok" }
}
```

### Constraints

- `pubkey` must be a 64-character hex string and already registered via `/api/nostr/register/`
- `recipients` is optional (`[]` is fine). Maximum **500** pubkeys per request.
- `recipients` are validated but the server silently skips any that aren't registered (no error, just no WS push to unregistered pubkeys).

---

## 3. Last-Active API — Batch Query (Polling Fallback)

Use this to populate the chat list when the app opens, or every minute in background, or when a conversation is first loaded.

### Request

```javascript
async function queryLastActive(pubkeys) {
  const res = await fetch('https://watchtower.cash/api/nostr/last-active/', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ pubkeys }),
  });

  if (!res.ok) throw new Error('Last-active query failed');

  return await res.json();
  // Shape: { "<pubkey_hex>": "2026-06-29T06:58:06.003828Z", "<other>": null }
}
```

### Example

```javascript
const pubkeys = [
  'f9a70a99c295d3a0753bf92e365c83f33b03d7c50f7876f2b81cfbf2084d8660',
  'aabbcc...',
];

const statuses = await queryLastActive(pubkeys);

for (const [pubkey, timestamp] of Object.entries(statuses)) {
  if (timestamp) {
    const ageMs = Date.now() - new Date(timestamp).getTime();
    if (ageMs < 180_000) {
      showGreenDot(pubkey);
    } else {
      hideGreenDot(pubkey);
    }
  } else {
    hideGreenDot(pubkey); // never active / not registered
  }
}
```

### Constraints

- Maximum **500** pubkeys per request (same cap as the old endpoint).
- Returns `null` for unregistered or never-active pubkeys.
- Responses are **cached in Redis for 24 hours** with DB fallback on cache miss, so this is cheap to poll.

---

## Recommended Frontend Flow

1. **App open / chat list visible**
   - Connect WebSocket for your own `wallet_hash`
   - Start 30s heartbeat
   - Call `queryLastActive()` for all visible contacts to get initial state

2. **You send a chat message**
   - Publish via Nostr relay (gift-wrap)
   - Immediately call `touchAfterSend()` with sender + recipient pubkeys
   - Recipients receive real-time WS push → green dot lights up

3. **You receive a WS `last_active` event**
   - Show green dot for that pubkey
   - Start 3-minute timer; hide when expired

4. **Periodic background poll**
   - Every 60s, call `queryLastActive()` for contacts on screen
   - Refreshes state for anyone whose WebSocket was disconnected

5. **App backgrounded / chat list hidden**
   - Close WebSocket cleanly
   - Stop heartbeat
