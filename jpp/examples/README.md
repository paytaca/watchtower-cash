# JPP WebSocket Examples

This directory contains example clients for testing the JPP invoice payment WebSocket endpoint.

## Overview

The WebSocket endpoint allows real-time monitoring of JPP invoice payments. When a payment is made to an invoice, all connected WebSocket clients will receive an immediate notification with the payment details.

## Endpoint

```
ws://localhost:8000/ws/jpp/invoice/{invoice_uuid}/
wss://watchtower.cash/ws/jpp/invoice/{invoice_uuid}/
```

## Examples

### 1. Python Client (`websocket_client_example.py`)

A command-line Python client for monitoring invoice payments.

**Installation:**
```bash
pip install websocket-client
```

**Usage:**
```bash
# Connect to local development server
python websocket_client_example.py 1234567890abcdef1234567890abcdef

# Connect to production server
python websocket_client_example.py 1234567890abcdef1234567890abcdef watchtower.cash
```

### 2. Node.js Client (`websocket_client_example.js`)

A command-line Node.js client for monitoring invoice payments.

**Installation:**
```bash
npm install ws
```

**Usage:**
```bash
# Connect to local development server
node websocket_client_example.js 1234567890abcdef1234567890abcdef

# Connect to production server
node websocket_client_example.js 1234567890abcdef1234567890abcdef watchtower.cash
```

### 3. HTML/JavaScript Client (`websocket_client_example.html`)

A browser-based testing interface with a visual log of all WebSocket events.

**Usage:**
Simply open the HTML file in a web browser, enter the server host and invoice UUID, then click "Connect".

## Message Format

When a payment is received, clients will receive a JSON message with the following structure:

```json
{
  "type": "payment_received",
  "invoice": {
    "payment_id": "1234567890abcdef...",
    "payment_url": "https://watchtower.cash/jpp/invoices/...",
    "network": "main",
    "currency": "BCH",
    "required_fee_per_byte": 1.1,
    "memo": "Invoice description",
    "time": "2025-10-23T12:00:00Z",
    "expires": "2025-10-23T12:30:00Z",
    "outputs": [
      {
        "amount": 10000,
        "address": "bitcoincash:qp..."
      }
    ],
    "payment": {
      "txid": "abc123...",
      "memo": "Payment memo",
      "paid_at": "2025-10-23T12:15:00Z",
      "refund_to": []
    }
  },
  "txid": "abc123...",
  "paid_at": "2025-10-23T12:15:00Z",
  "memo": "Payment memo"
}
```

## Testing

To test the WebSocket endpoint:

1. Create a JPP invoice:
   ```bash
   curl -X POST http://localhost:8000/jpp/invoices/ \
     -H "Content-Type: application/json" \
     -d '{
       "outputs": [
         {
           "amount": 10000,
           "address": "bitcoincash:qp..."
         }
       ],
       "memo": "Test invoice"
     }'
   ```

2. Note the `payment_id` (UUID) from the response

3. Connect to the WebSocket using one of the example clients:
   ```bash
   python websocket_client_example.py <payment_id>
   ```

4. Make a payment to the invoice:
   ```bash
   curl -X POST http://localhost:8000/jpp/invoices/<payment_id>/pay \
     -H "Content-Type: application/json" \
     -d '{
       "raw_tx_hex": "0100000001..."
     }'
   ```

5. The WebSocket client should receive the payment notification immediately

## Integration

To integrate this WebSocket endpoint into your application:

1. Connect to `ws://your-host/ws/jpp/invoice/{invoice_uuid}/` when displaying an invoice
2. Listen for `message` events
3. Parse the JSON data to extract payment details
4. Update your UI to show the payment received status
5. Close the connection when done

See the HTML example for a complete browser-based integration example.

