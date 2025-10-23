# WebSocket Security Guidelines

## Overview

This document provides security guidelines for implementing WebSocket consumers in the Watchtower system, particularly for transaction and payment monitoring endpoints.

## Critical Security Rule

**Transaction monitoring WebSocket consumers MUST be read-only.**

❌ **NEVER** implement `receive()`, `receive_json()`, or `receive_bytes()` methods in transaction monitoring consumers.

## Why This Matters

If a consumer accepts messages from clients and relays them to channel groups, malicious clients could:

1. Send fake transaction/payment data through the WebSocket
2. Have that data broadcast to all other connected clients
3. Cause other clients to mistakenly trust fake data as coming from the server

## Safe Consumer Pattern

```python
from channels.generic.websocket import WebsocketConsumer
from asgiref.sync import async_to_sync
import json

class SafeTransactionConsumer(WebsocketConsumer):
    """
    SECURITY: This consumer is READ-ONLY. It does not implement receive() to prevent
    clients from sending fake transaction updates that could be relayed to others.
    """
    
    def connect(self):
        # Extract parameters from URL
        self.resource_id = self.scope['url_route']['kwargs'].get('resource_id')
        self.room_name = f"resource_{self.resource_id}"
        
        # Join channel group
        async_to_sync(self.channel_layer.group_add)(
            self.room_name,
            self.channel_name
        )
        
        # Accept connection
        self.accept()
    
    def disconnect(self, close_code):
        # Leave channel group
        async_to_sync(self.channel_layer.group_discard)(
            self.room_name,
            self.channel_name
        )
    
    def send_update(self, event):
        """
        Called when server sends message to channel group.
        This is the ONLY way messages should be sent to clients.
        """
        data = event.get('data', {})
        self.send(text_data=json.dumps(data))
    
    # NO receive() method!
    # NO receive_json() method!
    # NO receive_bytes() method!
```

## How to Trigger Updates Safely

Updates must ONLY be triggered from server-side code:

```python
from channels.layers import get_channel_layer
from asgiref.sync import async_to_sync

def notify_transaction_update(resource_id, transaction_data):
    """
    Server-side function to send updates to WebSocket clients.
    Called from serializers, tasks, signals, etc.
    """
    channel_layer = get_channel_layer()
    room_name = f"resource_{resource_id}"
    
    # This is server-side code - trusted source
    async_to_sync(channel_layer.group_send)(
        room_name,
        {
            "type": "send_update",  # Calls the send_update() method
            "data": transaction_data
        }
    )
```

## Current Safe Implementations

All transaction monitoring consumers in Watchtower follow this pattern:

- ✅ `jpp/consumer.py` - `InvoicePaymentConsumer`
- ✅ `main/consumer.py` - `Consumer` (address/wallet watcher)
- ✅ `smartbch/consumer.py` - `TransactionTransferUpdatesConsumer`
- ✅ `rampp2p/consumers.py` - `OrderUpdatesConsumer`, `GeneralUpdatesConsumer`

## When `receive()` is Acceptable

The `receive()` method is acceptable for **RPC-style consumers** that:

1. Only respond directly to the requesting client (not broadcast)
2. Never relay client messages to channel groups
3. Validate and process specific RPC methods
4. Are designed for bidirectional communication

### Example: Safe RPC Consumer

```python
class SafeRPCConsumer(AsyncJsonWebsocketConsumer):
    async def receive(self, text_data=None, bytes_data=None, **kwargs):
        # Parse RPC request
        request = parse_request(text_data)
        
        # Process and respond ONLY to this client
        result = await self.handle_request(request)
        
        # Send response directly to requesting client
        await self.send(text_data=json.dumps(result))
        
        # Does NOT broadcast to channel groups!
```

**Examples in codebase:**
- `main/rpc_consumer.py` - RPC-style queries and subscriptions
- `paytacapos/consumer/rpc_consumer.py` - POS device RPC

## Security Checklist

When creating a new WebSocket consumer for transaction monitoring:

- [ ] Does NOT implement `receive()` method
- [ ] Does NOT implement `receive_json()` method
- [ ] Does NOT implement `receive_bytes()` method
- [ ] Only implements `send_update()` to receive server messages
- [ ] Includes security documentation in docstring
- [ ] Updates triggered only by server-side `channel_layer.group_send()`
- [ ] No client input is relayed to other clients

## Testing

Test that clients cannot inject fake updates:

```python
from channels.testing import WebsocketCommunicator
import pytest

async def test_client_cannot_send_messages():
    communicator = WebsocketCommunicator(
        SafeTransactionConsumer.as_asgi(),
        "/ws/path/to/resource/"
    )
    
    connected, _ = await communicator.connect()
    assert connected
    
    # Try to send data from client
    await communicator.send_json_to({
        'fake': 'transaction',
        'amount': 999999
    })
    
    # Should NOT receive anything (no receive method to process it)
    with pytest.raises(asyncio.TimeoutError):
        await communicator.receive_json_from(timeout=1)
    
    await communicator.disconnect()
```

## Code Review Guidelines

When reviewing WebSocket consumer code:

1. **Reject PRs** that add `receive()` methods to transaction monitoring consumers
2. **Require security documentation** in consumer docstrings
3. **Verify** updates are only sent via `channel_layer.group_send()`
4. **Check** that no client input is relayed to channel groups

## Summary

| Consumer Type | Can have receive()? | Why? |
|--------------|---------------------|------|
| Transaction monitoring | ❌ NO | Prevents fake transaction injection |
| Payment monitoring | ❌ NO | Prevents fake payment injection |
| RPC/Query | ✅ YES | Only responds to sender, doesn't relay |
| Bidirectional chat | ✅ YES | Designed for client messaging with auth |

**Default rule:** If in doubt, **do not implement receive()**.

## References

- Django Channels Security: https://channels.readthedocs.io/en/stable/topics/security.html
- WebSocket Security: https://owasp.org/www-community/websocket_security
- Channel Layers: https://channels.readthedocs.io/en/stable/topics/channel_layers.html

