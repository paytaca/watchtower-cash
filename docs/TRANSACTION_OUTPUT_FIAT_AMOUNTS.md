# Transaction Output Fiat Amounts

## Overview

The `output_fiat_amounts` field in `TransactionBroadcast` allows storing the exact user-entered fiat amounts for each transaction output. This preserves the precise amount typed by the user, independent of exchange rate fluctuations or rounding errors.

## Use Case

When a user sends a token transaction and enters a fiat amount (e.g., "100.50 PHP"), we need to:
1. Store the exact entered amount
2. Map it to specific transaction outputs
3. Recover the exact amount later for display/reconciliation

## Data Structure

The `output_fiat_amounts` is a JSON field with the following format:

```json
{
  "0": {
    "fiat_amount": "100.50",
    "fiat_currency": "PHP",
    "recipient": "bitcoincash:qr2z7dusk64qn960h9ktfkqk5cgqoh09vvpkd7pqqm",
    "token_amount": "5890.12345678",
    "token_category": "b38a33f750f84c5c169a6f23cb873e6e79605021585d4f3408789689ed87f366"
  },
  "1": {
    "fiat_amount": "50.25",
    "fiat_currency": "PHP",
    "recipient": "bitcoincash:qp3xn7p9jl7svqgvh9kqwwvwqx5qrqvqqcm8tqmq5x",
    "token_amount": "2945.06172839",
    "token_category": "b38a33f750f84c5c169a6f23cb873e6e79605021585d4f3408789689ed87f366"
  }
}
```

### Field Descriptions

| Field | Type | Description |
|-------|------|-------------|
| Key (output index) | string | The index of the transaction output (e.g., "0", "1", "2") |
| `fiat_amount` | string | Exact fiat amount entered by user (e.g., "100.50") |
| `fiat_currency` | string | Currency code (e.g., "USD", "PHP", "EUR") |
| `recipient` | string | Recipient address for this output |
| `token_amount` | string (optional) | Token amount being sent to this output |
| `token_category` | string (optional) | Token category hash if CashToken |

## API Usage

### Method 1: Broadcasting a Transaction with Fiat Amounts (Optional)

**Endpoint:** `POST /api/broadcast/`

**Request Body:**
```json
{
  "transaction": "0200000001...",
  "price_id": 3043712,
  "output_fiat_amounts": {
    "0": {
      "fiat_amount": "100.50",
      "fiat_currency": "PHP",
      "recipient": "bitcoincash:qr2z7dusk64qn960h9ktfkqk5cgqoh09vvpkd7pqqm",
      "token_amount": "5890.12345678",
      "token_category": "b38a33f750f84c5c169a6f23cb873e6e79605021585d4f3408789689ed87f366"
    },
    "1": {
      "fiat_amount": "50.25",
      "fiat_currency": "PHP",
      "recipient": "bitcoincash:qp3xn7p9jl7svqgvh9kqwwvwqx5qrqvqqcm8tqmq5x",
      "token_amount": "2945.06172839",
      "token_category": "b38a33f750f84c5c169a6f23cb873e6e79605021585d4f3408789689ed87f366"
    }
  }
}
```

**Response:**
```json
{
  "success": true,
  "txid": "abc123..."
}
```

### Method 2: Saving Fiat Amounts After Broadcast (Recommended)

This is the recommended approach - broadcast the transaction first, then save fiat amounts after it succeeds.

#### Step 1: Broadcast Transaction

**Endpoint:** `POST /api/broadcast/`

**Request Body:**
```json
{
  "transaction": "0200000001...",
  "price_id": 3043712
}
```

**Response:**
```json
{
  "success": true,
  "txid": "abc123..."
}
```

#### Step 2: Save Output Fiat Amounts

**Endpoint:** `POST /api/broadcast/output-fiat-amounts/`

**Request Body:**
```json
{
  "txid": "abc123...",
  "output_fiat_amounts": {
    "0": {
      "fiat_amount": "100.50",
      "fiat_currency": "PHP",
      "recipient": "bitcoincash:qr2z7dusk64qn960h9ktfkqk5cgqoh09vvpkd7pqqm",
      "token_amount": "5890.12345678",
      "token_category": "b38a33f750f84c5c169a6f23cb873e6e79605021585d4f3408789689ed87f366"
    },
    "1": {
      "fiat_amount": "50.25",
      "fiat_currency": "PHP",
      "recipient": "bitcoincash:qp3xn7p9jl7svqgvh9kqwwvwqx5qrqvqqcm8tqmq5x",
      "token_amount": "2945.06172839",
      "token_category": "b38a33f750f84c5c169a6f23cb873e6e79605021585d4f3408789689ed87f366"
    }
  }
}
```

**Response (Success):**
```json
{
  "success": true,
  "txid": "abc123...",
  "message": "Output fiat amounts saved successfully"
}
```

**Response (Conflict - data already exists):**
```json
{
  "success": false,
  "error": "Output fiat amounts already exist for this transaction. Cannot overwrite.",
  "existing_data": {
    "0": {
      "fiat_amount": "100.50",
      "fiat_currency": "PHP",
      ...
    }
  }
}
```

**Status Codes:**
- `200 OK`: Successfully saved
- `400 Bad Request`: Invalid request data
- `404 Not Found`: Transaction not found
- `409 Conflict`: Fiat amounts already exist (cannot overwrite)

### Retrieving Output Fiat Amounts

**Endpoint:** `GET /api/broadcast/output-fiat-amounts/{txid}/`

**Example:** `GET /api/broadcast/output-fiat-amounts/abc123.../`

**Response:**
```json
{
  "success": true,
  "txid": "abc123...",
  "output_fiat_amounts": {
    "0": {
      "fiat_amount": "100.50",
      "fiat_currency": "PHP",
      "recipient": "bitcoincash:qr2z7dusk64qn960h9ktfkqk5cgqoh09vvpkd7pqqm",
      "token_amount": "5890.12345678",
      "token_category": "b38a33f750f84c5c169a6f23cb873e6e79605021585d4f3408789689ed87f366"
    },
    "1": {
      "fiat_amount": "50.25",
      "fiat_currency": "PHP",
      "recipient": "bitcoincash:qp3xn7p9jl7svqgvh9kqwwvwqx5qrqvqqcm8tqmq5x",
      "token_amount": "2945.06172839",
      "token_category": "b38a33f750f84c5c169a6f23cb873e6e79605021585d4f3408789689ed87f366"
    }
  }
}
```

## Retrieving Fiat Amounts

### Via Django ORM

```python
from main.models import TransactionBroadcast

# Get transaction broadcast record
tx_broadcast = TransactionBroadcast.objects.get(txid='abc123...')

# Access output fiat amounts
if tx_broadcast.output_fiat_amounts:
    for output_index, details in tx_broadcast.output_fiat_amounts.items():
        print(f"Output {output_index}:")
        print(f"  Fiat Amount: {details['fiat_amount']} {details['fiat_currency']}")
        print(f"  Recipient: {details['recipient']}")
        print(f"  Token Amount: {details.get('token_amount', 'N/A')}")
```

### Via Admin Interface

The Django admin displays a "Has Fiat Amounts" column showing which transactions have fiat amount data stored.

## Benefits

1. **Precision**: Stores exact user-entered amounts without rounding errors
2. **Output-Level Granularity**: Maps amounts to specific transaction outputs
3. **Currency Flexibility**: Supports any fiat currency
4. **Recovery**: Can recover exact fiat amounts for display or reconciliation
5. **Backward Compatible**: Optional field, existing transactions unaffected
6. **Security**: Once saved, fiat amounts cannot be overwritten, preventing tampering

## Example Use Cases

### 1. Multi-Recipient Payments
User sends 100 PHP to Alice and 50 PHP to Bob in a single transaction:
- Output 0 (to Alice): 100.00 PHP
- Output 1 (to Bob): 50.00 PHP
- Both amounts preserved exactly as entered

### 2. Price Verification
Compare the user-entered amount with the calculated amount using exchange rates to verify accuracy or detect discrepancies.

### 3. Transaction History Display
Show users exactly what they entered when they sent the transaction, not a recalculated value based on current rates.

## Migration

Run migrations to add the field:
```bash
python manage.py makemigrations
python manage.py migrate
```

## Related

- `price_log`: Stores the exchange rate used at transaction time
- `AssetPriceLog`: Contains market price data
- `WalletHistory`: Transaction history records that can reference this data

