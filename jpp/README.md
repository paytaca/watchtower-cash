# JSON Payment Protocol
Watchtower's API for BIP70 payments

## API
- POST:`/jpp/invoices/`
  - create an invoice in watchtower
- GET: `/jpp/invoices/{uuid}/`
  - retrieves a single invoice
- POST: `/jpp/invoices/{uuid}/verify`
  - verify an unsigned transaction if it satifies the required amount for each output address 
- POST: `/jpp/invoices/{uuid}/pay`
  - submit a signed transaction hex as payment to an invoice
  - broadcasts & saves the tx hex to db
  - validates the transaction hex before broadcasting
- GET, POST: `jpp/i/{uuid}/`
  - APIs that follow Bitcoin.com's implementation
- GET, POST: `jpp/i/bitpay/{uuid}/`
  - APIs that follow Bitpay's implementation

## WebSocket API

### Invoice Payment Updates
Listen for real-time payment updates on a JPP invoice.

**Endpoint:** `ws/jpp/invoice/{invoice_uuid}/`

**Example:**
```javascript
// Connect to WebSocket
const invoiceUuid = '1234567890abcdef';
const ws = new WebSocket(`wss://watchtower.cash/ws/jpp/invoice/${invoiceUuid}/`);

ws.onopen = () => {
  console.log('Connected to invoice payment updates');
};

ws.onmessage = (event) => {
  const data = JSON.parse(event.data);
  console.log('Payment received:', data);
  
  // data structure:
  // {
  //   type: 'payment_received',
  //   invoice: { ...full invoice details... },
  //   txid: '...',
  //   paid_at: '...',
  //   memo: '...'
  // }
};

ws.onerror = (error) => {
  console.error('WebSocket error:', error);
};

ws.onclose = () => {
  console.log('Disconnected from invoice payment updates');
};
```

**Response Data:**
When a payment is made to the invoice, connected clients will receive:
```json
{
  "type": "payment_received",
  "invoice": {
    "payment_id": "1234567890abcdef",
    "payment_url": "...",
    "network": "main",
    "currency": "BCH",
    "required_fee_per_byte": 1.1,
    "memo": "...",
    "time": "...",
    "expires": "...",
    "outputs": [...],
    "payment": {
      "txid": "...",
      "memo": "...",
      "paid_at": "...",
      "refund_to": [...]
    }
  },
  "txid": "transaction_hash",
  "paid_at": "2025-10-23T12:34:56Z",
  "memo": "Payment memo"
}
```
