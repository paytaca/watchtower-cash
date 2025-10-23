# JPP WebSocket Security

## Security Model

### Read-Only WebSocket Consumers

All transaction monitoring WebSocket endpoints (`/ws/watch/*`, `/ws/jpp/invoice/*`, etc.) are **read-only**. They only push updates from the server to clients.

**Critical Security Rule:**
> Never implement `receive()`, `receive_json()`, or `receive_bytes()` methods in transaction monitoring consumers.

### Why This Matters

If a consumer accepts messages from clients and relays them to a channel group, malicious clients could:

1. Connect to the WebSocket
2. Send fake transaction/payment data
3. Have that data broadcast to all other connected clients
4. Other clients mistakenly trust the fake data as coming from the server

### Example of UNSAFE Consumer

```python
# ❌ DANGEROUS - DO NOT DO THIS
class UnsafeConsumer(WebsocketConsumer):
    def connect(self):
        self.room_name = "transactions"
        async_to_sync(self.channel_layer.group_add)(
            self.room_name,
            self.channel_name
        )
        self.accept()
    
    def receive_json(self, content):
        # DANGEROUS: This relays client messages to all connected clients!
        async_to_sync(self.channel_layer.group_send)(
            self.room_name,
            {
                "type": "send_update",
                "data": content  # Fake transaction data from malicious client
            }
        )
```

### Example of SAFE Consumer

```python
# ✓ SAFE - Current JPP implementation
class InvoicePaymentConsumer(WebsocketConsumer):
    def connect(self):
        self.invoice_uuid = self.scope['url_route']['kwargs'].get('invoice_uuid')
        self.room_name = f"jpp_invoice_{self.invoice_uuid}"
        
        async_to_sync(self.channel_layer.group_add)(
            self.room_name,
            self.channel_name
        )
        self.accept()
    
    def disconnect(self, close_code):
        async_to_sync(self.channel_layer.group_discard)(
            self.room_name,
            self.channel_name
        )
    
    def send_update(self, event):
        # Only receives messages from server-side channel_layer.group_send()
        data = event.get('data', {})
        self.send(text_data=json.dumps(data))
    
    # NO receive() or receive_json() method!
    # Clients cannot send messages that get processed or relayed
```

## How Updates Are Safely Triggered

Updates can **only** be triggered by server-side code:

```python
# In serializers.py or other server-side code
def send_invoice_payment_update(invoice_obj, payment_obj):
    channel_layer = get_channel_layer()
    room_name = f"jpp_invoice_{invoice_obj.uuid.hex}"
    
    # This is server-side code - trusted source
    async_to_sync(channel_layer.group_send)(
        room_name,
        {
            "type": "send_update",
            "data": {
                "txid": payment_obj.txid,
                "paid_at": str(payment_obj.paid_at),
                # ... trusted data from database
            }
        }
    )
```

## Message Flow

### Safe (Current Implementation)

```
Database Transaction Created
         ↓
Server-side Code (serializer/task/signal)
         ↓
channel_layer.group_send()
         ↓
Consumer.send_update() method
         ↓
WebSocket Client Receives Update
```

Clients **cannot inject** into this flow because they have no way to call `channel_layer.group_send()`.

### Unsafe (What to Avoid)

```
Malicious Client
         ↓
WebSocket send({fake: "transaction"})
         ↓
Consumer.receive_json() method
         ↓
channel_layer.group_send()  ← DANGER!
         ↓
All Connected Clients Receive Fake Data
```

## RPC-Style Consumers

Some consumers (like `main/rpc_consumer.py` and `paytacapos/consumer/rpc_consumer.py`) do implement `receive()` for RPC-style communication. These are safe because:

1. They only respond directly to the requesting client
2. They never relay client messages to channel groups
3. They validate and process specific RPC methods
4. They're designed for bidirectional communication (subscriptions, queries)

### Safe RPC Pattern

```python
class RPCWebSocketConsumer(AsyncJsonWebsocketConsumer):
    async def receive(self, text_data=None, bytes_data=None, **kwargs):
        request = parse_rpc_request(text_data)
        
        # Process request and respond ONLY to this client
        result = await self.handle_rpc_request(request)
        
        # Send response directly to requesting client
        await self.send(text_data=json.dumps(result))
        
        # Does NOT broadcast to channel groups!
```

## Audit Checklist

When creating or reviewing a WebSocket consumer for transaction monitoring:

- [ ] Consumer does NOT implement `receive()` method
- [ ] Consumer does NOT implement `receive_json()` method  
- [ ] Consumer does NOT implement `receive_bytes()` method
- [ ] Updates are only sent via `send_update()` method
- [ ] `send_update()` only receives events from `channel_layer.group_send()`
- [ ] Server-side code is the only source of `channel_layer.group_send()` calls
- [ ] Consumer documentation includes security notes

## Testing for Vulnerabilities

Test that clients cannot send fake updates:

```python
from channels.testing import WebsocketCommunicator
from jpp.consumer import InvoicePaymentConsumer

async def test_client_cannot_send_fake_update():
    invoice = Invoice.objects.create(...)
    
    communicator = WebsocketCommunicator(
        InvoicePaymentConsumer.as_asgi(),
        f"/ws/jpp/invoice/{invoice.uuid.hex}/"
    )
    
    connected, _ = await communicator.connect()
    assert connected
    
    # Try to send fake transaction data
    await communicator.send_json_to({
        'txid': 'fake_transaction',
        'amount': 999999
    })
    
    # Should NOT receive anything back
    # Consumer should ignore the message (no receive method)
    with pytest.raises(TimeoutError):
        await communicator.receive_json_from(timeout=1)
```

## Summary

**For transaction monitoring WebSocket endpoints:**
- ✅ Implement: `connect()`, `disconnect()`, `send_update()`
- ❌ Never implement: `receive()`, `receive_json()`, `receive_bytes()`
- ✅ Updates triggered by: Server-side `channel_layer.group_send()`
- ❌ Updates never triggered by: Client messages

This ensures clients can only listen, never broadcast fake data.

