# Paytaca Gifts Documentation

## Overview

Paytaca Gifts is a system that allows users to send Bitcoin Cash (BCH) as gifts using a secure, shareable link. The system uses **Shamir's Secret Sharing Algorithm** to split a private key into multiple shards, ensuring that the gift can only be claimed by someone who has the correct gift code.

## Security Model: Shamir's Secret Sharing

### Algorithm Overview

Paytaca Gifts implements a **2-of-3 threshold** Shamir's Secret Sharing scheme:

- A private key is split into **3 shards** using Shamir's Secret Sharing
- **2 out of 3 shards** are required to reconstitute the private key
- This provides redundancy and security - if one shard is lost, the gift can still be claimed

### Shard Distribution

The three shards are distributed as follows:

1. **Shard 1 (Plaintext)**: Stored in the `share` field in the database
2. **Shard 2 (Encrypted)**: Stored in the `encrypted_share` field, encrypted with the gift code
3. **Shard 3**: Not stored in the database (presumably kept by the gift creator or another party)

### Gift Code

The **gift code** is a secret key that:
- Is used to encrypt the second shard (`encrypted_share`)
- Is required to decrypt `encrypted_share` and claim the gift
- Can be optionally encrypted and stored in the database as `encrypted_gift_code`

The gift code is hashed using SHA-256 to create the `gift_code_hash`, which is used to identify and look up gifts in the database:

```python
gift_code_hash = SHA256(gift_code)
```

#### Encrypted Gift Code Storage

To solve the problem of storing the gift code on the client device (which is not amenable to wallet export/import), the gift code can be encrypted and stored in the database:

- **Encryption Method**: The gift code is encrypted using the private key of the **index 0 address** in the HD wallet used by the client app that created the gift
- **Storage**: The encrypted value is stored in the `encrypted_gift_code` field
- **Recovery**: When a wallet is restored from a seed phrase, the client can decrypt `encrypted_gift_code` using the private key of the index 0 address to recover the gift code
- **Optional**: This field is optional - gifts can be created with or without it, depending on whether the client wants to enable wallet export/import functionality

## Database Schema

### Gift Model

The `Gift` model stores the following key fields:

- `gift_code_hash` (CharField, max_length=70, unique=True): SHA-256 hash of the gift code, used to identify the gift
- `address` (CharField, max_length=64): The Bitcoin Cash address where the gift funds are stored
- `amount` (FloatField): The amount of BCH in the gift
- `share` (CharField, max_length=255): **Shard 1** - One of the three shards stored in plaintext
- `encrypted_share` (TextField, default=''): **Shard 2** - One of the three shards encrypted with the gift code
- `encrypted_gift_code` (TextField, default='', blank=True): **Optional** - The gift code encrypted with the private key of the index 0 address in the HD wallet
- `date_funded` (DateTimeField): When the gift address was funded
- `date_claimed` (DateTimeField): When the gift was claimed
- `claim_txid` (CharField): Transaction ID of the claim transaction
- `wallet` (ForeignKey): The wallet that created the gift
- `campaign` (ForeignKey, optional): Optional campaign the gift belongs to

## Gift Lifecycle

### 1. Gift Creation

**Endpoint**: `POST /api/gifts/{wallet_hash}/create/`

**Request Payload**:

For a gift without a campaign:
```json
{
  "gift_code_hash": "sha256_hash_of_gift_code",
  "address": "bitcoin_cash_address",
  "share": "plaintext_shard_1",
  "encrypted_share": "encrypted_shard_2",
  "encrypted_gift_code": "encrypted_gift_code_value",
  "amount": 0.001
}
```

For a gift with a **new campaign**:
```json
{
  "gift_code_hash": "sha256_hash_of_gift_code",
  "address": "bitcoin_cash_address",
  "share": "plaintext_shard_1",
  "encrypted_share": "encrypted_shard_2",
  "encrypted_gift_code": "encrypted_gift_code_value",
  "amount": 0.001,
  "campaign": {
    "name": "Campaign Name",
    "limit_per_wallet": 0.01
  }
}
```

For a gift with an **existing campaign**:
```json
{
  "gift_code_hash": "sha256_hash_of_gift_code",
  "address": "bitcoin_cash_address",
  "share": "plaintext_shard_1",
  "encrypted_share": "encrypted_shard_2",
  "encrypted_gift_code": "encrypted_gift_code_value",
  "amount": 0.001,
  "campaign": {
    "id": "existing_campaign_uuid"
  }
}
```

**Process**:
1. Client generates a gift code (secret key)
2. Client splits the private key into 3 shards using Shamir's Secret Sharing
3. Client encrypts shard 2 with the gift code
4. Client optionally encrypts the gift code with the private key of the index 0 address in the HD wallet
5. Client sends `gift_code_hash` (SHA-256 of gift code), `share` (shard 1), `encrypted_share` (encrypted shard 2), and optionally `encrypted_gift_code` to the server
6. Server handles campaign association:
   - If `campaign.limit_per_wallet` is provided, creates a new campaign with the given name and limit
   - If `campaign.id` is provided, associates the gift with the existing campaign
   - If `campaign` is omitted, the gift is not associated with any campaign
7. Server stores the gift record and subscribes to the address for transaction monitoring
8. The gift code itself is **never sent to the server in plaintext**

**Security Note**: The server cannot decrypt `encrypted_share` or `encrypted_gift_code` because it never receives the gift code or the HD wallet private key.

### 2. Gift Claiming

**Endpoint**: `POST /api/gifts/{gift_code_hash}/claim` or `POST /api/gifts/{gift_code_hash}/claim/` (both supported for backward compatibility)

**Request Payload**:
```json
{
  "wallet_hash": "claiming_wallet_hash",
  "transaction_hex": "optional_transaction_hex_ready_for_broadcast"
}
```

**Response**:
```json
{
  "share": "plaintext_shard_1",
  "encrypted_share": "encrypted_shard_2",
  "encrypted_gift_code": "encrypted_gift_code_value",
  "claim_id": "uuid"
}
```

**Process**:
1. Client provides the `gift_code_hash` to identify the gift
2. If `transaction_hex` is provided:
   - Server tests mempool acceptance of the transaction
   - If accepted, server broadcasts the transaction **synchronously**
   - If broadcast fails, the claim request fails with an error
   - Only proceeds with claim creation if broadcast succeeds
3. Server returns `share` (shard 1), `encrypted_share` (shard 2), and `encrypted_gift_code` (if present)
4. Client obtains the gift code:
   - If the client has the gift code from the original link, use it directly
   - If the client has restored the wallet from a seed phrase, decrypt `encrypted_gift_code` using the private key of the index 0 address
5. Client uses the gift code to decrypt `encrypted_share`
6. Client now has 2 shards (shard 1 + decrypted shard 2)
7. Client uses Shamir's Secret Sharing to reconstitute the private key
8. Client uses the private key to claim the funds from the gift address

**Transaction Broadcasting**:
- The `transaction_hex` field is **optional**
- If provided, the transaction will be broadcast synchronously before the gift is marked as claimed
- The broadcast uses the same endpoint logic as `/api/broadcast/` but executes synchronously
- If the transaction is rejected by the mempool or broadcast fails, the claim request will fail
- This ensures that the gift is only marked as claimed if the transaction is successfully broadcast

**Security Note**: Without the gift code, only one shard is available (insufficient to reconstitute the private key). The `encrypted_gift_code` can only be decrypted by the wallet that created the gift (using the index 0 private key).

### 3. Gift Recovery

**Endpoint**: `POST /api/gifts/{gift_code_hash}/recover`

**Request Payload**:
```json
{
  "wallet_hash": "original_wallet_hash"
}
```

**Response**:
```json
{
  "share": "plaintext_shard_1",
  "encrypted_share": "encrypted_shard_2",
  "encrypted_gift_code": "encrypted_gift_code_value"
}
```

**Process**:
1. The original gift creator can recover the gift if it hasn't been claimed
2. Server returns `share` (shard 1), `encrypted_share` (shard 2), and `encrypted_gift_code` (if present)
3. Creator obtains the gift code:
   - If they have the gift code from the original creation, use it directly
   - If they have restored the wallet from a seed phrase, decrypt `encrypted_gift_code` using the private key of the index 0 address
4. Creator uses the gift code to decrypt `encrypted_share`
5. Creator reconstitutes the private key and recovers the funds

## Security Considerations

### Why This Design is Secure

1. **Gift Code Never Leaves Client in Plaintext**: The gift code is never transmitted to or stored on the server in plaintext. If `encrypted_gift_code` is used, it is encrypted with the HD wallet's private key, making it impossible for the server to decrypt `encrypted_share` even if compromised.

2. **2-of-3 Threshold**: Requires 2 shards to reconstitute the private key, providing redundancy while maintaining security.

3. **Hash-Based Lookup**: The `gift_code_hash` allows the server to identify gifts without knowing the actual gift code, preventing server-side decryption.

4. **Encrypted Shard Protection**: The `encrypted_share` is useless without the gift code, even if an attacker gains access to the database.

5. **Wallet Export/Import Support**: The `encrypted_gift_code` field enables wallet export/import functionality. When a wallet is restored from a seed phrase, the client can decrypt `encrypted_gift_code` using the index 0 private key to recover the gift code, allowing access to previously created gifts.

### Attack Scenarios

- **Database Compromise**: An attacker with database access would only have:
  - Shard 1 (plaintext `share`)
  - Shard 2 (encrypted `encrypted_share`)
  - Encrypted gift code (`encrypted_gift_code`, if present)
  - Without the gift code or the HD wallet's private key, they cannot decrypt shard 2 or the gift code, so they cannot reconstitute the private key

- **Network Interception**: Even if network traffic is intercepted, the gift code is never transmitted in plaintext, so the attacker cannot decrypt `encrypted_share`

- **Server Compromise**: A compromised server cannot decrypt gifts because it never receives the gift code in plaintext or the HD wallet's private key needed to decrypt `encrypted_gift_code`

## API Endpoints

### List Gifts
- **Endpoint**: `GET /api/gifts/{wallet_hash}/list/`
- **Description**: Fetches a list of gifts for a wallet with pagination
- **Query Parameters**: `offset`, `limit`, `claimed`, `campaign`
- **Response**: Includes `encrypted_gift_code` field for each gift (if present)

### Create Gift
- **Endpoint**: `POST /api/gifts/{wallet_hash}/create/`
- **Description**: Creates a new gift record
- **Request Body**: `CreateGiftPayloadSerializer`
- **Note**: `encrypted_gift_code` is optional in the request payload

### Claim Gift
- **Endpoint**: `POST /api/gifts/{gift_code_hash}/claim` or `POST /api/gifts/{gift_code_hash}/claim/` (both supported for backward compatibility)
- **Description**: Claims a gift and returns the shards needed to reconstitute the private key. Optionally accepts a transaction hex for synchronous broadcasting.
- **Request Body**: `ClaimGiftPayloadSerializer`
  - `wallet_hash` (required): The wallet hash of the claiming wallet
  - `transaction_hex` (optional): Transaction hex ready for broadcast. If provided, will be broadcast synchronously before marking the gift as claimed.
- **Response**: `ClaimGiftResponseSerializer` (includes `share`, `encrypted_share`, and `encrypted_gift_code` if present)
- **Transaction Broadcasting**: If `transaction_hex` is provided:
  - The transaction is tested for mempool acceptance
  - If accepted, it is broadcast synchronously
  - The gift is only marked as claimed if the broadcast succeeds
  - If broadcast fails, the claim request fails with an appropriate error message
- **Backward Compatibility**: The endpoint supports both trailing slash and no trailing slash formats. The `encrypted_gift_code` field in the response is optional and will be an empty string if not present, ensuring compatibility with older clients. The `transaction_hex` field is optional, so existing clients continue to work without modification.

### Recover Gift
- **Endpoint**: `POST /api/gifts/{gift_code_hash}/recover`
- **Description**: Recovers a gift (for the original creator)
- **Request Body**: `RecoverGiftPayloadSerializer`
- **Response**: `RecoverGiftResponseSerializer` (includes `share`, `encrypted_share`, and `encrypted_gift_code` if present)

## Data Flow Diagram

```
┌─────────────┐
│   Client    │
│  (Creator)  │
└──────┬──────┘
       │
       │ 1. Generate gift code
       │ 2. Split private key into 3 shards
       │ 3. Encrypt shard 2 with gift code
       │
       ▼
┌─────────────────────────────────────┐
│  POST /api/gifts/{wallet_hash}/create/│
│  - gift_code_hash (SHA256 of code) │
│  - share (shard 1, plaintext)      │
│  - encrypted_share (shard 2, enc)   │
│  - address, amount                  │
└──────────────┬──────────────────────┘
               │
               ▼
┌─────────────────────────────────────┐
│         Server (Database)            │
│  - Stores gift_code_hash             │
│  - Stores share (shard 1)            │
│  - Stores encrypted_share (shard 2)  │
│  - Never receives gift code          │
└──────────────┬──────────────────────┘
               │
               │ Gift link shared with recipient
               ▼
┌─────────────┐
│   Client    │
│ (Recipient) │
└──────┬──────┘
       │
       │ 1. Has gift code (from link)
       │ 2. POST /api/gifts/{hash}/claim
       │
       ▼
┌─────────────────────────────────────┐
│         Server Response             │
│  - share (shard 1)                  │
│  - encrypted_share (shard 2)        │
└──────────────┬──────────────────────┘
               │
               ▼
┌─────────────────────────────────────┐
│   Client (Recipient)                │
│  1. Decrypt encrypted_share         │
│     using gift code                 │
│  2. Now has shard 1 + shard 2       │
│  3. Reconstitute private key        │
│  4. Claim funds from address        │
└─────────────────────────────────────┘
```

## Implementation Details

### Gift Code Hash Generation

The gift code hash is generated using SHA-256:

```python
import hashlib

def generate_gift_code_hash(gift_code):
    return hashlib.sha256(gift_code.encode()).hexdigest()
```

### Field Storage

- `share`: Stored as `CharField(max_length=255)` - plaintext shard
- `encrypted_share`: Stored as `TextField(default='')` - encrypted shard (changed from CharField to TextField in migration 0007 to support longer encrypted values)
- `encrypted_gift_code`: Stored as `TextField(default='', blank=True)` - optional encrypted gift code, encrypted with the HD wallet's index 0 private key

### Migration History

- **Migration 0006**: Added `encrypted_share` field as `CharField`
- **Migration 0007**: Changed `encrypted_share` from `CharField` to `TextField` to support longer encrypted values
- **Migration 0008**: Added `encrypted_gift_code` field as `TextField` to support wallet export/import functionality

## Best Practices

1. **Gift Code Security**: The gift code should be:
   - Generated using cryptographically secure random number generation
   - Shared securely with the recipient (e.g., via secure link, QR code)
   - Never logged or stored in plaintext on the client
   - Optionally encrypted with the HD wallet's index 0 private key and stored as `encrypted_gift_code` to enable wallet export/import

2. **Encryption**: The encryption of shard 2 should use:
   - Strong encryption algorithm (e.g., AES-256)
   - Proper key derivation from the gift code
   - Authenticated encryption if possible

3. **Shamir's Secret Sharing**: Use a well-tested library for Shamir's Secret Sharing implementation to ensure:
   - Proper polynomial generation
   - Secure random coefficients
   - Correct threshold reconstruction

## Related Models

### Wallet
- Represents a wallet that can create and claim gifts
- Identified by `wallet_hash`

### Campaign
- Optional grouping of gifts
- Can have `limit_per_wallet` to restrict claiming
- Useful for promotional campaigns

### Claim
- Records gift claims
- Links a wallet to a gift
- Tracks claim success status
- Enforces unique constraint: one claim per wallet per gift

## Summary

Paytaca Gifts provides a secure way to send Bitcoin Cash as gifts by:

1. Using Shamir's Secret Sharing to split private keys into 3 shards (2-of-3 threshold)
2. Storing one shard in plaintext (`share`) and one encrypted (`encrypted_share`)
3. Using a gift code (never stored on server in plaintext) to encrypt/decrypt the second shard
4. Optionally storing the gift code encrypted with the HD wallet's index 0 private key (`encrypted_gift_code`) to enable wallet export/import
5. Requiring the gift code to claim the gift, ensuring only the intended recipient can access funds

This design ensures that even if the server is compromised, gifts cannot be claimed without the gift code, providing strong security guarantees. The optional `encrypted_gift_code` field solves the wallet export/import problem by allowing gift codes to be recovered when a wallet is restored from a seed phrase.

