# Nostr Typing Status — Frontend Integration Guide

## Overview

Typing indicators are delivered over the same WebSocket connection used for
last-active (green dot) status. No new endpoint or REST call is needed.

| Resource | URL | Purpose |
|----------|-----|---------|
| **WebSocket** | `wss://watchtower.cash/ws/nostr/updates/<wallet_hash>/` | Send typing signals; receive real-time typing events from contacts |

The server derives the sender's identity from the authenticated WebSocket
connection — the client never sends its own pubkey, only the `room_id` and
`recipients`.

---

## 1. Send a Typing Signal

When the user starts typing in a chat room, send a `typing` message over the
existing WebSocket connection:

```javascript
function sendTyping(ws, roomId, recipientPubkeys) {
  if (ws.readyState !== WebSocket.OPEN) return;

  ws.send(JSON.stringify({
    type: 'typing',
    room_id: roomId,
    recipients: recipientPubkeys, // e.g. ["b_pubkey_hex", "c_pubkey_hex"]
  }));
}
```

### Throttling

The server applies a **3-second throttle** per sender pubkey per room. If a
typing signal arrives within the throttle window, the server silently drops it
(no error, no close). The client should also throttle locally to avoid
sending redundant messages:

```javascript
let lastTypingSent = 0;
const TYPING_THROTTLE_MS = 3000; // 3s — must match server throttle

function onTextInput(ws, roomId, recipientPubkeys) {
  const now = Date.now();
  if (now - lastTypingSent < TYPING_THROTTLE_MS) return;
  lastTypingSent = now;
  sendTyping(ws, roomId, recipientPubkeys);
}
```

### Message Format

```json
{
  "type": "typing",
  "room_id": "<room_id>",
  "recipients": ["<64-char hex pubkey>", ...]
}
```

### Constraints

- `room_id` is required and must be a string.
- `recipients` is required, must be a non-empty list of 64-character hex
  pubkeys, max **500** entries.
- If either field is missing/invalid, the server closes the WebSocket with
  code `4001`.
- The sender's pubkey is derived from the authenticated connection — do not
  include it in the message.

---

## 2. Receive a Typing Event

When a contact starts typing, the server pushes a `typing` event to your
WebSocket:

```javascript
ws.onmessage = (event) => {
  const msg = JSON.parse(event.data);

  if (msg.type === 'typing') {
    handleTyping(msg.pubkey_hex, msg.room_id);
  } else if (msg.type === 'last_active') {
    handleLastActive(msg.pubkey_hex, msg.timestamp);
  }
};
```

### Event Shape

```json
{
  "type": "typing",
  "pubkey_hex": "<sender_pubkey_hex>",
  "room_id": "<room_id>"
}
```

### Auto-Hide Logic

Show the typing indicator when an event arrives, then auto-hide it after
**5 seconds** if no new typing event is received for the same pubkey + room:

```javascript
const typingTimers = new Map(); // `${pubkey}:${room_id}` -> timeoutId

function handleTyping(pubkeyHex, roomId) {
  const key = `${pubkeyHex}:${roomId}`;
  showTypingIndicator(pubkeyHex, roomId);

  if (typingTimers.has(key)) {
    clearTimeout(typingTimers.get(key));
  }

  const timeoutId = setTimeout(() => {
    hideTypingIndicator(pubkeyHex, roomId);
    typingTimers.delete(key);
  }, 5000); // 5s

  typingTimers.set(key, timeoutId);
}
```

---

## 3. Privacy

Typing indicators respect the existing `show_active_status` privacy toggle:

- If the **sender** has `show_active_status=False`, their typing signals are
  never broadcast to anyone.
- If the **recipient** has `show_active_status=False`, they will not receive
  typing events from anyone.

This is the same mutual-consent model used by last-active/green-dot status.
No additional privacy controls are needed.

---

## 4. Recommended Frontend Flow

1. **User opens a chat room**
   - WebSocket is already connected (for heartbeats / last-active)
   - On text input, call `sendTyping()` at most every 3 seconds

2. **You receive a WS `typing` event**
   - Show "X is typing..." in the matching room
   - Start/reset a 5-second auto-hide timer

3. **User stops typing or leaves the room**
   - No explicit "stop typing" message is needed
   - The 5-second timer on the recipient side will auto-hide the indicator

4. **User sends a message**
   - Continue sending heartbeats as normal
   - Call `touchAfterSend()` as before — the recipient's typing indicator
     is unrelated to the last-active push

---

## 5. Error Handling

| Scenario | Server behavior |
|----------|----------------|
| Missing `room_id` or `recipients` | Closes WebSocket with code `4001` |
| Invalid recipient pubkey (not 64-char hex) | Closes WebSocket with code `4001` |
| More than 500 recipients | Closes WebSocket with code `4001` |
| Unrecognized message type | Closes WebSocket with code `4001` |
| Sender has `show_active_status=False` | Silently dropped (no broadcast) |
| Recipient has `show_active_status=False` | Silently dropped (no forward) |
| Within 3s throttle window | Silently dropped (no broadcast) |
| Recipient not registered on watchtower | Silently skipped (no WS push) |

If the WebSocket is closed with code `4001`, the client should reconnect with
backoff and re-send only valid messages.
