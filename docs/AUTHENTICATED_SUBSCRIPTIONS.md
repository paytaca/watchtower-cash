# Watchtower Authenticated Address-Pair Subscriptions

**Status:** Proposed specification (v0.2) — supersedes v0.1
**Scope:** Paytaca Watchtower; standard Bitcoin Cash P2PKH receiving/change addresses
**Goal:** Prevent unauthorized wallet subscriptions and subscriptions to addresses for which the requester cannot demonstrate key control, without disclosing mnemonics, private keys, or extended public keys (xpubs).

**v0.2 changes.** v0.1 left the three items that block implementation — the seed-to-key
derivation, the canonical challenge encoding, and the server audience binding — as open
questions. This revision fixes all three, supplies normative test vectors, and corrects
several places where the described behaviour did not match watchtower-cash as it exists.
Section 12 lists every change and the defect it closes.

---

## 0. Terminology and conventions

| Term | Meaning |
|---|---|
| `SHA256(x)` | SHA-256 over the byte string `x` |
| `HASH160(x)` | `RIPEMD160(SHA256(x))` |
| `\|\|` | byte concatenation |
| `u32`, `u64` | big-endian unsigned integers |
| compressed pubkey | 33 bytes, SEC1, prefix `0x02`/`0x03` |
| `walletId` | 32 raw bytes; hex lowercase in transport |
| MUST / MUST NOT / SHOULD / MAY | RFC 2119 |

All hex in this document is lowercase. All byte lengths are exact unless stated otherwise.
Signature material, public keys, and challenges MUST be rejected, not truncated, when a
length differs.

---

## 1. Security model

Watchtower maintains a many-to-many relationship between wallet identities and monitored
addresses. A wallet may subscribe to many addresses; an address may appear under multiple
wallets. Watchtower does not need to establish that addresses are derived from the same HD
seed. It must establish:

1. **Wallet authorization** — the requester controls the authentication private key
   corresponding to the wallet identity.
2. **Receiving-address control** — the requester controls the private key for the claimed
   receiving P2PKH address.
3. **Change-address control** — the requester controls the private key for the claimed
   change P2PKH address.

A successful subscription requires **three valid signatures** over one canonical,
server-issued challenge: authentication-key, receiving-key, and change-key.

**Non-goals.** This asserts nothing about a shared mnemonic, derivation path, or HD account.
A client holding three unrelated keys may register them together; that is intentional.
It also asserts nothing about *reads* (Section 9.1).

**Trust boundary.** The proof is a statement about key possession at registration time. It
is not proof of reserves, not proof of continued key retention, and not proof that the
reported balance is spendable by the requester.

---

## 2. Key derivation and wallet identity

### 2.1 Normative derivation

The authentication key MUST be derived from the BIP39 seed exactly as follows. Anything
else — HKDF output used directly as a scalar, a non-hardened path, a different mnemonic
normalization — is out of spec and MUST be considered a different identity.

```
purpose = 2092950013                     # 0x7CBFE1FD, see 2.1.1
path    = m/2092950013'/0'/0'            # all three levels hardened
```

Algorithm:

1. `seed = PBKDF2-HMAC-SHA512(NFKD(mnemonic), "mnemonic" || NFKD(passphrase), 2048, 64)`
   (BIP39; this is what `Bip39SeedGenerator(...).Generate(passphrase)` computes).
2. `m = BIP32_master(seed)` (BIP32; HMAC-SHA512 keyed by `"Bitcoin seed"`).
3. Descend the three hardened levels above using standard BIP32 child derivation.
4. `authPrivKey = k` from the resulting `(k, K)` pair; `authPubKey = K` compressed.

**Why a hardened BIP32 path instead of HKDF.** BIP32 child derivation already guarantees a
valid scalar: if the derived `IL >= n` (probability ~2⁻¹²⁷) BIP32 mandates skipping to the
next index, and every conforming implementation does this. HKDF gives no such guarantee and
would need a bespoke rejection-sampling step that cannot be interoperable unless specified
byte-for-byte. Reusing BIP32 buys a well-tested failure mode for free.

**Why all three levels hardened.** The authentication key is derived from public seed
material and is deliberately *not* random per wallet. A non-hardened level would let anyone
holding the parent xpub recompute the key. Hardening the full path means no xpub of any
suffix can produce it. This is the reason the path has three levels rather than being a
single hardened index.

**This key MUST NOT** be used to sign blockchain transactions, to derive addresses, or for
any other protocol. It exists only to authorize Watchtower calls.

#### 2.1.1 The purpose index

`2092950013` is `0x7CBFE1FD`, which is the first four bytes of
`SHA256("Paytaca Watchtower Auth Key v1")` masked to 31 bits. It is a SLIP-0043-style
purpose index: arbitrary but fixed, reproducible from the string, and outside the range
of currently assigned purposes. Implementations MUST hardcode the integer, not recompute
it at runtime; the hash is recorded here only to document where the number came from.

#### 2.1.2 Passphrase handling

The BIP39 passphrase MUST be the one the user entered, NFKD-normalized, and MUST default
to `""`. It MUST NOT be silently dropped when non-empty, and MUST NOT be used as a
"25th word" heuristic. A wallet that supported a passphrase before v0.1 and now omits it
will derive a different `walletId` — recovery from seed MUST therefore prompt for the
passphrase, exactly as it does for address derivation.

### 2.2 Self-certifying wallet identifier

```
walletId = SHA256("Paytaca Watchtower Wallet ID v1" || authPubKey)
```

`authPubKey` is the 33-byte compressed key (not hex). `walletId` is 32 bytes, transported as
64 lowercase hex characters.

Watchtower MUST recompute `walletId` from the submitted `authPubKey` and compare in constant
time. It MUST NOT accept a client-chosen `walletId`. The domain separator prevents an
`authPubKey` committed under this scheme from being confused with the same key used to
commit to something else.

This is a **new identity namespace**. It is not cryptographically bound to the legacy
`SHA256(mnemonic || derivationPath)` hash. See Section 11.

### 2.3 Test vectors

Mnemonic (standard BIP39 all-`abandon` vector):

```
abandon abandon abandon abandon abandon abandon abandon abandon abandon abandon abandon about
```

| passphrase | seed | authPrivKey | authPubKey | walletId |
|---|---|---|---|---|
| `""` | `5eb00bbddcf069084889a8ab9155568165f5c453ccb85e70811aaed6f6da5fc19a5ac40b389cd370d086206dec8aa6c43daea6690f20ad3d8d48b2d2ce9e38e4` | `60268048bc7f02fe05ab631d42c4223a6d8da7b0c6fa77d65fa38f7e5c9d99de` | `03f9d71ac67d1abbd5fbfb3357fdc3125df31029c088d6d658500a32cd5cf67389` | `92f03a224c1026fb354566dab4deb17dd6b1bf79012707ca083734b619808a2a` |
| `"TREZOR"` | `c55257c360c07c72029aebc1b53c05ed0362ada38ead3e3e9efa3708e53495531f09a6987599d18264c1e1c92f2cf141630c7a3c4ab7c81b2f001698e7463b04` | `3c26c44e00eb0d32aa2c46bfc6fe750caa556ba399d39f6dc6e9d16af7444c27` | `02d96a474d0bb2baa26ac772130595fad933893c126870edbddd74b2f1df70dd88` | `0557aec7c28cb649c4ef4e851f74673e19890b628f4386e5b5f1294686fb109b` |

Client and server test suites MUST both assert row 1. A client that reproduces `authPubKey`
but not `walletId` has a domain-separator bug; one that reproduces neither has a
derivation bug.

---

## 3. Protocol primitives

- **Signature algorithm:** secp256k1 ECDSA, deterministic per RFC 6979, over
  `SHA256(canonicalEncode(challenge))`. DER-encoded, **low-S only** (Section 3.3).
- **Public keys:** compressed SEC1, 33 bytes, prefix `0x02` or `0x03`. Validated by
  decompressing onto the curve.
- **Addresses:** canonical BCH CashAddr, P2PKH, expected network and type. Compare on the
  20-byte `HASH160` payload, never on the string (Section 3.4).
- **Nonce:** 32 bytes from a CSPRNG.
- **Expiration:** 120 seconds from issue, checked server-side.
- **Replay protection:** one-use challenge, consumed atomically (Section 8.2).
- **Transport:** TLS required. TLS is not the authorization mechanism.

### 3.1 Canonical challenge encoding

Challenges are encoded as a fixed-layout binary structure, **not** JSON. Length-prefixed
fields in fixed order; no optional fields, no key ordering to agree on, no number-formatting
to agree on.

```
magic          : 8 bytes   "WTCHAL1\0"  (57 54 43 48 41 4c 31 00)
audience       : u16 length + UTF-8 bytes
network        : u8        (table below)
operation      : u8        (table below)
payload        : operation-specific
nonce          : 32 bytes  CSPRNG
expiresAt      : u64       Unix seconds, UTC
challengeId    : u16 length + UTF-8 bytes  (opaque, 8..64 chars)
```

`network`:

| value | network |
|---|---|
| 0 | mainnet (`bitcoincash:`) |
| 1 | chipnet / testnet (`bchtest:`) |

`operation`:

| value | operation | payload |
|---|---|---|
| 1 | `register_wallet` | `authPubKey` (33 bytes) |
| 2 | `subscribe_pair` | `walletId` (32) ‖ `index` (u32) ‖ `receivingH160` (20) ‖ `changeH160` (20) |
| 3 | `unsubscribe_pair` | `walletId` (32) ‖ `subscriptionId` (32) |
| 4 | `replace_pair` | `walletId` (32) ‖ `index` (u32) ‖ `oldReceivingH160` (20) ‖ `oldChangeH160` (20) ‖ `receivingH160` (20) ‖ `changeH160` (20) |

The digest is `challengeDigest = SHA256(canonicalBytes)`. All required keys sign this same
digest. Every field above is inside the digest, so any change to network, operation,
audience, index, addresses, nonce, expiry, or challenge ID invalidates all three signatures.

**Registration payload uses the pubkey, not the derived `walletId`.** The server can derive
`walletId` from the key but not the reverse, so binding the pubkey is strictly stronger: it
pins the single value that defines the identity.

**Field lengths are fixed by construction** except `audience` and `challengeId`, whose `u16`
prefixes make the total length unambiguous. Encoders MUST NOT emit a `u16` prefix on any
other field. Decoders MUST reject trailing bytes after the last field.

### 3.2 Audience

`audience` is the deployment's canonical host, lowercase, no scheme, no port, no trailing
slash — e.g. `watchtower.paytaca.com`. It is **mandatory in v1**, not optional as in v0.1.

Chipnet and mainnet are separate deployments running identical code, so the signing domain
is genuinely shared; without an audience a signature collected on one is replayable against
the other. The `network` byte alone is not sufficient: two mainnet deployments (production
and a staging host on mainnet) would collide. Servers MUST reject a challenge whose audience
differs from their configured value, and MUST reject an empty audience.

### 3.3 Signature encoding rules

The verifier MUST enforce, in this order:

1. Total DER length 8..72 bytes and exactly equal to the parsed structure's length
   (no trailing bytes — a DER signature with a suffix MUST fail).
2. Minimally-encoded DER integers: no leading `0x00` unless required to clear the sign bit;
   no length octets in long form when short form suffices.
3. `1 <= r < n` and `1 <= s <= n/2` where `n` is the secp256k1 group order. **Reject
   `s > n/2` outright** — do not normalize it into validity.
4. Decompression of the public key succeeds, giving a point on the curve.

These are not theoretical. The `ecdsa` library pinned in `requirements.txt` (0.18.0):
verifies **high-S** signatures happily, accepts **64-byte uncompressed** public keys, and
its `sigdecode_der` will happily decode `r` values that the low-S rule must reject.
Every rule above must be implemented explicitly; none is inherited from the library.

Signers MUST produce low-S, minimally encoded DER. `sigencode_der_canonize` does this;
plain `sigencode_der` does **not** and will emit high-S roughly half the time.

### 3.4 Address normalization

On receipt of a CashAddr, Watchtower MUST:

1. Parse with a CashAddr decoder that verifies the checksum. Prefix (network) and
   checksum are bound together, so a `bchtest:` string fails checksum validation under the
   `bitcoincash:` prefix — cross-network confusion is prevented at parse time.
2. Reject legacy base58 (`1...`/`3...`) input. The decoder used in this repo accepts legacy
   strings transparently; the endpoint MUST NOT.
3. Reject anything other than lowercase.
4. Require 20-byte payload and P2PKH version for the expected network
   (`P2PKH` on mainnet, `P2PKH-TESTNET` on testnet).
5. Compare `bytes(payload)` against `HASH160(pubkey)` byte-for-byte.

A 32-byte payload parses as `version=P2PKH` under this decoder and MUST be rejected by the
length check. Token-aware (`z`-prefix) addresses use a different version nibble and MUST be
rejected.

### 3.5 Canonical encoding vectors

Inputs: mnemonic as in 2.3, passphrase `""`, `audience = "watchtower.paytaca.com"`,
`network = 0`, `index = 5`, `nonce = 000102…1f` (32 bytes, `00` through `1f`),
`expiresAt = 1767225600`, `challengeId = "5f3a9c1e8b2d4a6f9c0e1d2b3a4f5e6d"`.

Derived with `m/2092950013'/0'/0'/0/5` and `…/1/5`:

| | value |
|---|---|
| receivingPubKey | `02b6d2f23ac811becddba8aae8322d2465364e681edf8127f06cfeefeddfec2021` |
| receivingAddress | `bitcoincash:qr8mquxjgdrjjsh7s4qghcct3nr2s2vnsudq6yvqzf` |
| changePubKey | `03cbd2161c45bd205587c10e90d4e69a1969cdd1c2880099a292f76c3f4bc4415c` |
| changeAddress | `bitcoincash:qr5t7rn89xh6n66wqzz9weq5lgujvxpygqcfce33hz` |

**`subscribe_pair`, 184 bytes:**

```
57544348414c310000167761746368746f7765722e706179746163612e636f6d0002
92f03a224c1026fb354566dab4deb17dd6b1bf79012707ca083734b619808a2a0000
0005cfb070d243472942fe85408be30b8cc6a8299387e8bf0e6729afa9eb4e008457
6414fa3926182440000102030405060708090a0b0c0d0e0f10111213141516171819
1a1b1c1d1e1f000000006955b9000020356633613963316538623264346136663963
3065316432623361346635653664
```

(Line breaks are for readability only; the canonical byte string is the concatenation of
all lines.)

**`challengeId` is opaque ASCII, not hex-decoded.** The string
`"5f3a9c1e8b2d4a6f9c0e1d2b3a4f5e6d"` is 32 characters, so its UTF-8 encoding is 32 bytes
and appears in the canonical form as `3566336139633165…` (the ASCII codes, not the nibble
values). It is 32 bytes either way, which is exactly why this is easy to get wrong; a client
that hex-decodes the ID produces a different digest and a failing signature.

| field | offset | length |
|---|---|---|
| magic | 0 | 8 |
| `u16` len(audience) | 8 | 2 |
| audience | 10 | 22 |
| network | 32 | 1 |
| operation | 33 | 1 |
| walletId | 34 | 32 |
| index | 66 | 4 |
| receivingH160 | 70 | 20 |
| changeH160 | 90 | 20 |
| nonce | 110 | 32 |
| expiresAt | 142 | 8 |
| `u16` len(challengeId) | 150 | 2 |
| challengeId | 152 | 32 |

| | value |
|---|---|
| digest | `0295bc1d5328c0276a824f44de12c3fa11a74bb0393767447a8cf674a49c356e` |
| authSignature | `30440220656a09b5f0bde57e8a2a76a8c398d58acdda9ad6578bb47e7fab31e84b545164022019d7669c21ad3cc1fea15ce31b10cdc0209742adeb23293c1efac71c06eeccdb` |
| receivingSignature | `3045022100d00643b366661cbb49d29e8c388c1688f6bd621b7826265529672ebde1650c44022076983628f42ebe4e506e7785bdfbb7a2b81c159b4e88bd40636c503643885b8a` |
| changeSignature | `3044022064838865cb3175428a4f85ed0b73707d45e223acf2cd3aace40f53774c0bccab02201a000fc5b3b1e514a9964b75c1055d641540eb122226fa4bb683d1c08aa67e02` |

**`register_wallet`, 141 bytes:**

```
57544348414c310000167761746368746f7765722e706179746163612e636f6d0001
03f9d71ac67d1abbd5fbfb3357fdc3125df31029c088d6d658500a32cd5cf6738900
0102030405060708090a0b0c0d0e0f101112131415161718191a1b1c1d1e1f000000
006955b9000020356633613963316538623264346136663963306531643262336134
6635653664
```

| | value |
|---|---|
| digest | `6f49ef7d612c586a2ab95eb3db8dc3ef6f2246fdc2c85460d183f3e69be23c9b` |
| signature | `304402207f616c6ca61be3ea40e75b3ba015da7309a4b4a4567150990a5a2b32181ea41902204f0ea4ff1bdad9c8f2035f8dc47741f720400f908f4309cb326676552c8dc461` |

These vectors are internally consistent: the `subscribe_pair` digest changes if any single
byte of the challenge changes, and each signature verifies only under its own key.

---

## 4. API flows

Naming follows existing Watchtower conventions (`/api/...`). Envelope details are
illustrative; the signed bytes are not.

### 4.1 Wallet registration

**`POST /api/wallet/challenge`**

```json
{ "operation": "register_wallet", "authPublicKey": "03f9d7...7389" }
```

Response:

```json
{
  "challengeId": "5f3a9c1e8b2d4a6f9c0e1d2b3a4f5e6d",
  "canonical": "<hex of the exact bytes to sign>",
  "expiresAt": 1767225600,
  "walletId": "92f03a...8a2a"
}
```

`canonical` is returned so clients need not implement the encoder to interoperate in the
short term; clients SHOULD nevertheless implement it, because the server re-derives the
bytes and a client relying on the blob cannot detect a server that encodes differently.

**`POST /api/wallet`**

```json
{
  "walletId": "<64 hex>",
  "authPublicKey": "<66 hex>",
  "challengeId": "<opaque>",
  "signature": "<DER hex>"
}
```

Watchtower MUST:

1. Parse and validate the compressed pubkey; reject 64-byte and `0x04`-prefixed forms.
2. Recompute `walletId` and compare exactly (constant time).
3. Load the challenge; verify it is unconsumed, unexpired, of operation
   `register_wallet`, of the configured audience and network, and that its `authPubKey`
   field equals the submitted key.
4. Verify the signature under `authPublicKey` with Section 3.3 rules.
5. Consume the challenge (Section 8.2) and create the wallet atomically.

**Idempotency.** Re-posting the same `(authPublicKey, walletId)` for an existing wallet MUST
return the same success as the original call, with the original `walletId`. This applies
even though the second call's challenge is already consumed — the idempotent path MUST be
evaluated against the stored wallet before challenge lookup, otherwise legitimate client
retries after a network timeout produce spurious 409s.

**Conflicts.** If `walletId` exists with a different `authPublicKey`, return `409`. Because
`walletId` is a digest of the key, this is only reachable by a hash collision or a corrupt
row; treat it as an integrity error and alert, not as a user error.

Registration MUST be rate-limited and MUST NOT be reachable without a challenge. An
unauthenticated "create wallet from pubkey" endpoint reintroduces exactly the v0.1 hole.

### 4.2 Obtain subscription challenge

**`POST /api/wallet/{walletId}/subscriptions/challenge`**

```json
{
  "index": 5,
  "receivingAddress": "bitcoincash:qr8mquxjgdrjjsh7s4qghcct3nr2s2vnsudq6yvqzf",
  "changeAddress": "bitcoincash:qr5t7rn89xh6n66wqzz9weq5lgujvxpygqcfce33hz"
}
```

The server normalizes and validates both addresses (Section 3.4), checks the index fits
`u32` and is below the configured per-wallet cap, then issues a challenge bound to the exact
`walletId`, index, both `HASH160` payloads, audience, network, and `subscribe_pair`.

The address is normalized to its `HASH160` before being placed in the challenge and again
at verification. Normalizing at both points means a client that submits the same address in
two encodings cannot obtain one signature that satisfies both.

**Rejecting the degenerate case.** If `receivingH160 == changeH160`, the challenge endpoint
MUST reject with `400`. Otherwise "three signatures" silently degrades to two distinct keys,
and a client could satisfy the protocol while proving control of only two addresses. If a
future requirement needs a wallet that legitimately shares receiving and change at an index,
it needs an explicitly specified weaker verification method with its own identifier, not a
silent collapse.

### 4.3 Subscribe address pair

**`POST /api/wallet/{walletId}/subscriptions`**

```json
{
  "challengeId": "<opaque>",
  "index": 5,
  "receivingAddress": "bitcoincash:qr8m...yvqzf",
  "changeAddress": "bitcoincash:qr5t...33hz",
  "receivingPublicKey": "02b6d2...2021",
  "changePublicKey": "03cbd2...415c",
  "authSignature": "<DER hex>",
  "receivingSignature": "<DER hex>",
  "changeSignature": "<DER hex>"
}
```

Watchtower MUST:

1. Load the registered `authPublicKey` for `{walletId}`; 404 if unknown.
2. Load the challenge; reject if unknown, consumed, or expired.
3. Reject if the challenge's `walletId`, index, `receivingH160`, `changeH160`, operation,
   audience, or network differ from the request's (after normalization). Comparison is on
   the reconstructed canonical bytes, not on re-derived fields one by one.
4. Verify `authSignature` under the registered key.
5. Decode both CashAddrs: P2PKH, expected network, 20-byte payload (§3.4).
6. Verify `HASH160(receivingPublicKey) == receivingH160` and likewise for change. Both
   keys MUST parse as 33-byte compressed points.
7. Verify `receivingSignature` and `changeSignature` under their respective keys over the
   same digest, with every Section 3.3 rule applied.
8. Atomically consume the challenge and upsert the subscription (Section 8.2).
9. Enforce `UNIQUE(walletId, index)`. A conflicting row at the same index whose addresses
   differ MUST be rejected with `409` naming the `replace_pair` operation; it MUST NOT be
   overwritten.
10. Return the stable `subscriptionId` and status.

**Order matters.** Steps 2–7 all run before the consume in step 8, and the consume is what
makes the challenge unusable. Verifying after consuming would let an attacker burn another
wallet's challenge by replaying garbage against it.

**Never** treat the presence of a public key, wallet ID, or address as authorization. If a
signature is missing, the request fails; there is no reduced-proof fallback path.

### 4.4 Unsubscribe and replace

Both require their own challenge with their own operation byte. Signatures collected for
`subscribe_pair` MUST NOT be accepted for either.

- **`unsubscribe_pair`** — payload binds `walletId` and `subscriptionId`. Requires **one**
  signature: the auth key. Address keys are not required, because the authorization being
  exercised is "this wallet may stop monitoring these addresses", and the wallet already
  proved address control at subscribe time. Requiring address-key signatures on deletion
  would make a subscription undeletable by a user who lost a key.
- **`replace_pair`** — payload binds the old and new address pairs. Requires **five**
  signatures: auth, old receiving, old change, new receiving, and new change. Rationale:
  removal is free to the key holder (as above) but *addition* always needs the full
  three-signature rule (Section 1), and replacing old with new is a removal plus an
  addition. Old-address signatures are required so one wallet cannot replace another
  wallet's binding for an address pair it does not control.

Replacement MUST be atomic: either the old pair is gone and the new pair is present, or
nothing changed.

---

## 5. Data model

```text
wallets(
  wallet_id            BYTEA(32) PRIMARY KEY,
  auth_public_key      BYTEA(33) UNIQUE NOT NULL,
  identity_version     SMALLINT NOT NULL,   -- 1 for this scheme
  created_at           TIMESTAMPTZ NOT NULL
)

address_pair_subscriptions(
  subscription_id      BYTEA(32) PRIMARY KEY,
  wallet_id            BYTEA(32) NOT NULL REFERENCES wallets(wallet_id) ON DELETE CASCADE,
  derivation_index     BIGINT NOT NULL,
  receiving_address    TEXT NOT NULL,
  change_address       TEXT NOT NULL,
  verification_method  TEXT NOT NULL,        -- 'three_signatures_v1'
  created_at           TIMESTAMPTZ NOT NULL,
  updated_at           TIMESTAMPTZ NOT NULL,
  UNIQUE (wallet_id, derivation_index)
)

challenges(
  challenge_id         TEXT PRIMARY KEY,
  audience             TEXT NOT NULL,
  network              SMALLINT NOT NULL,
  operation            SMALLINT NOT NULL,
  wallet_id            BYTEA(32) NULL,       -- NULL for register_wallet
  auth_public_key      BYTEA(33) NULL,       -- set for register_wallet
  canonical_payload    BYTEA NOT NULL,
  expires_at           TIMESTAMPTZ NOT NULL,
  consumed_at          TIMESTAMPTZ NULL
)
CREATE INDEX ON challenges (expires_at);
CREATE INDEX ON challenges (consumed_at) WHERE consumed_at IS NULL;
```

`wallet_id` in `challenges` **must be nullable**. v0.1's sketch made it `NOT NULL`, which
makes registration impossible: the challenge is issued before any wallet row exists. For
`register_wallet` it is `NULL` and `auth_public_key` is set; for the other three operations
the reverse. A `CHECK` constraint should enforce exactly one being set.

**Do not impose global uniqueness on an address.** The same address may be monitored by
multiple wallets, and this is the point of the whole design. Section 10 records what this
means for the current schema, which does enforce global uniqueness.

Index conflicts are resolved by `UNIQUE(wallet_id, derivation_index)` alone. Do **not**
copy the current `remove_duplicate_wallet_address_path` repair task forward — it resolves
conflicts by deleting subscriptions and recipients, which is a data-loss bug, not a
migration strategy.

---

## 6. Reads, balances, and what the proof does not cover

A successful three-signature transaction establishes key possession at that moment. It does
not establish that

- the addresses share a seed or derivation path;
- the wallet will still hold the keys later;
- the indexed balance is complete, or spendable by the requester.

Watchtower SHOULD report indexed UTXOs and balances as **monitored blockchain data**, not as
proof of reserves or collateral. Wallet clients SHOULD locally derive expected addresses and
validate returned UTXOs before displaying a spendable balance. Third-party financial
services MUST NOT treat an aggregate wallet balance as proof of ownership.

Signed writes do not authorize reads (Section 9.1).

---

## 7. Scope restrictions

Version 1 supports **single-key BCH P2PKH only**.

Rejected until separately specified: P2SH, multisig, CashTokens covenant/script addresses,
token-aware (`z`-prefix) address forms, and any other spending condition. These need a
proof-of-control scheme that binds a script template, not `HASH160(pubkey)`.

For P2PKH, a valid signature plus hash match demonstrates possession of the signing key. It
says nothing about script-based or multisignature outputs.

---

## 8. Abuse resistance

### 8.1 Limits

- Rate-limit challenge creation, registration, and subscription writes — keyed by
  `walletId` where known and by IP otherwise, with separate buckets per operation so
  registration floods cannot starve challenge refreshes.
- Cap active subscriptions per wallet (suggested initial value: 5,000) and outstanding
  challenges per wallet (suggested: 10).
- Enforce request size limits and strict parsers: exact field lengths, valid curve points,
  canonical DER, supported address formats only.
- Delete expired challenges on a schedule; keep `expiresAt` indexed for the sweep.
- Do not log signed challenge material, public keys, or addresses at INFO or above.
  Challenge bytes and digests belong in DEBUG-only paths, if anywhere.

### 8.2 Atomic consumption

The challenge consume and the subscription write belong in one database transaction:

```sql
UPDATE challenges
   SET consumed_at = now()
 WHERE challenge_id = %s
   AND consumed_at IS NULL
   AND expires_at > now()
RETURNING canonical_payload;
```

Then verify the signatures against the returned payload, and insert the subscription in the
same transaction. Zero rows affected means replay, expiry, or unknown ID — all `409`/`410`
with no further work.

This ordering is deliberate: the row lock makes concurrent replays serialize, and the
signature check happens under the lock so a second concurrent request cannot observe the
challenge as unconsumed. Verification failures roll back, leaving the challenge consumed —
which is correct, because a failed verification attempt should not hand the nonce back to
the caller.

Prefer Postgres over Redis for this. Redis has no cross-key transaction that gives the same
guarantee, and `UPDATE ... RETURNING` already provides the atomicity while keeping the
challenge in the durable store.

### 8.3 Cross-wallet isolation

Every wallet-scoped route MUST resolve `{walletId}` through the authenticated challenge, not
from the URL alone. A URL that names a target wallet plus a signature over a *different*
wallet's challenge is the obvious attack; it is prevented at step 3 of §4.3 but MUST also be
covered by a test (§10, test 13).

---

## 9. Privacy

- `authPublicKey` and `walletId` are stable pseudonymous identifiers, linkable across all
  of a wallet's subscriptions. This is a direct consequence of self-certifying identity and
  is accepted.
- Watchtower learns every monitored address. It already did. The signature scheme does not
  reduce that; address discovery on-chain still works.
- Per-index address pairs leak the numbering scheme to the server. Requests MUST NOT carry
  address paths, xpubs, or account identifiers beyond `index`.
- Do not correlate `walletId` with a legacy wallet hash in the same response or log line;
  that would defeat the migration boundary in Section 11.

### 9.1 Read authorization

This specification authorizes **writes** only. It does not define an authorization model
for reads, and signature material MUST NOT be repurposed as a bearer credential for them.

Reads are handled as follows until a separate read-authorization design exists:

- **Wallet-scoped routes** (`/api/wallet/{walletId}/...`) MUST require the caller to prove
  control of `authPublicKey` for that wallet on every request — a short-lived challenge
  signature, or a bearer token issued from one. A URL containing `walletId` MUST NOT be
  sufficient on its own.
- **Address-scoped routes** that predate this work remain unauthenticated, including
  `GET /api/balance/bch/{address}/`. That is a pre-existing property of the balance API and
  is unchanged by this document; it is recorded here so it is not mistaken for a gap this
  spec introduces or closes.
- Read endpoints MUST NOT be added on the assumption that a successful write proves
  authorization for later reads.

Acceptance test 13 covers wallet-scoped routes only; it must not be read as asserting
anything about address-scoped reads.

---

## 10. Acceptance tests

Each test names the observable assertion. Numbers 1–14 are from v0.1; 15–22 close gaps
found while writing v0.2.

1. Valid registration and three-signature subscription succeed; response carries a stable
   `subscriptionId`.
2. Wrong auth signature fails even with both address signatures valid.
3. Wrong receiving signature fails.
4. Wrong change signature fails.
5. Pubkey not matching the receiving/change `HASH160` fails.
6. Changing any of walletId, index, receiving address, change address, operation, network,
   audience, nonce, expiry, or challengeId fails.
7. Expired challenge fails; replays fail, **including concurrent replays** — two requests
   racing on one challenge produce exactly one success and one `409`.
8. A client cannot register another wallet's identity using its own auth pubkey.
9. Two different authenticated wallets subscribe to the same address, each with valid
   proof, and both subscriptions are independently retrievable.
10. A wallet subscribes unrelated keys it controls; no shared-seed claim is asserted or
    stored.
11. P2SH, multisig, script, and `z`-prefix addresses fail closed.
12. Restoring the same seed and passphrase reproduces the same auth key and `walletId` —
    asserted against §2.3, in both the client and the server suite.
13. Cross-wallet reads and writes are rejected unless separately authorized.
14. A conflicting subscription at the same `(walletId, index)` is rejected, or handled by
    `replace_pair`, and the pre-existing row is unchanged in the reject case.
15. High-S signature rejected. A high-S variant of a valid vector must fail (§3.3).
16. DER with trailing bytes rejected. Non-minimal DER integers rejected.
17. 64-byte uncompressed pubkey rejected; `0x04`-prefixed 33-byte rejected.
18. Legacy base58 address rejected; uppercase CashAddr rejected; a `bchtest:` address on a
    mainnet deployment rejected.
19. `receivingAddress == changeAddress` rejected at challenge creation (§4.2), not accepted
    as a two-signature proof.
20. Registration idempotency: posting the same key and `walletId` twice returns success
    both times; posting a different key for an existing `walletId` returns `409`.
21. Signature collected for `subscribe_pair` fails under `unsubscribe_pair` and
    `replace_pair` operations.
22. `canonical` bytes returned by the challenge endpoint re-hash to the digest the server
    verifies — i.e. the advertised blob matches the encoded challenge byte-for-byte.

---

## 11. Migration from legacy wallet hashes

The existing `SHA256(mnemonic || derivationPath)` identifier is **not** self-certifying.
Watchtower cannot establish that a newly presented auth key corresponds to that legacy hash
by checking a signature, because no key was ever bound to it. **First-claim-wins binding of a
legacy hash to a new auth key is prohibited** — it lets anyone who has seen a wallet hash
claim it.

Recommended rollout:

1. Introduce the new `walletId` namespace alongside legacy hashes. `identity_version`
   distinguishes them; the legacy path keeps its existing authorization model until step 4.
2. Ship client key derivation (§2.1) and registration. Clients verify their own
   `walletId` against §2.3 before registering.
3. Clients re-subscribe address pairs through the three-signature flow, in the background,
   while legacy subscriptions keep working.
4. After a measured adoption window, retire legacy write authorization: reject
   `POST /api/subscription/` bodies carrying only `wallet_hash` for wallets that have
   migrated. Keep it for wallets that have not, until the deprecation date.
5. Legacy associations remain marked unverified. If historical linkage is required, define
   a separate procedure with its own trust model — and do not assert cryptographic
   continuity between old and new IDs.

Migration MUST be per-wallet, not global, so a lagging client does not lose monitoring.

---

## 12. Changes from v0.1, and why

| # | v0.1 | v0.2 | Defect closed |
|---|---|---|---|
| 1 | Derivation "must be fixed before deployment"; HKDF mentioned with a warning | Fixed hardened BIP32 path, purpose derived from a hash, vectors given (§2.1) | Implementation was impossible; two clients could not agree on an identity |
| 2 | Canonical encoding "deterministic binary or canonical JSON" | Fixed byte layout with offsets and vectors (§3.1, §3.5) | Ambiguity → signature mismatch across platforms |
| 3 | Audience "if multiple deployments share a domain" (optional) | Mandatory (§3.2) | Chipnet/mainnet and prod/staging replay |
| 4 | Registration challenge fields unspecified | `register_wallet` payload binds `authPubKey` (§3.1) | Registration was unbound; replayable to any wallet |
| 5 | `challenges.wallet_id NOT NULL` | Nullable, with `auth_public_key` (§5) | Registration challenges could not be stored at all |
| 6 | Receiving == change not addressed | Rejected at challenge creation (§4.2, test 19) | "Three signatures" silently became two |
| 7 | `unsubscribe`/`replace` signature requirements left as "a policy decision" | Fixed: 1 auth signature to remove, 5 to replace (§4.4) | Deletion became impossible after key loss, or replacement became unauthenticated |
| 8 | Low-S mentioned once, in passing | Explicit 4-rule verifier spec (§3.3) with tests 15–16 | Pinned `ecdsa` 0.18.0 accepts high-S and 64-byte keys |
| 9 | Address comparison "compare the 20-byte payload" | Full normalization algorithm, legacy/z-prefix/length rejection (§3.4) | Decoder in this repo accepts base58 and 32-byte payloads |
| 10 | Idempotency "return an idempotent success" | Ordering specified: check stored wallet before challenge lookup (§4.1) | Retries after timeout returned spurious 409s |
| 11 | Consume "atomically" | `UPDATE … RETURNING` with verify-under-lock ordering (§8.2) | Verify-after-consume burned other wallets' challenges |
| 12 | Index conflicts "reject or handle" | `UNIQUE(walletId, index)` only; repair-by-deletion forbidden (§5) | Existing repair task deletes subscriptions/recipients |
| 13 | Test 13 "cross-wallet reads rejected" | Kept, plus a note that reads have no auth model yet (§9.1, §6) | Test was unsatisfiable as written |
| 14 | Test 12 "same seed reproduces identity" | Pinned to the §2.3 vectors | Test had no expected value |

### Deliberately left open

- **Per-wallet quotas** — needs production traffic data; §8.1 gives starting values.
- **Challenge sweep schedule** — operational, not protocol.
- **Read authorization** — out of scope. Note that `GET /api/balance/bch/{address}/` is
  currently unauthenticated; that is a pre-existing property of the balance API, not
  something this spec changes, and test 13 only covers wallet-scoped routes.

---

## 13. Implementation notes for this repository

Recorded so the implementer does not rediscover them. Nothing here changes the protocol.

- **`Address.address` is globally unique** (`main/models.py:202`) and `Address.wallet` is a
  single FK (`main/models.py:211`). The spec requires an address to belong to many wallets.
  `main/utils/subscription.py:212` assigns `address_obj.wallet = wallet` on each subscribe,
  silently reassigning an address away from its previous owner. Wallet ownership is joined
  in 99 places across 35 `.py` files repo-wide (62 in `main`, 21 files) via `address__wallet`
  and `wallet__wallet_hash`. Supporting multi-wallet addresses therefore needs an
  address↔wallet join table and a coordinated rewrite, not a field tweak. `Subscription`
  (address ↔ recipient) is already many-to-many and is the right shape to imitate.
- **Address validation currently shells out** to a Node service (`main/utils/address_converter.py`,
  `bch_address_converter`, `http://localhost:3000`). An authorization path must not depend
  on a best-effort HTTP call for a security decision; use the in-process `cashaddress`
  decoder and treat its failure as rejection.
- **Dependency drift:** `requirements.txt` pins `ecdsa==0.18.0` and `redis==4.3.4`; the venv
  has `ecdsa 0.19.2` and `redis 3.4.1`. Pin before relying on either behaviour. The crypto
  rules in §3.3 are written to hold under both `ecdsa` versions.
- `bip-utils` is already pinned (`2.9.3` in requirements; 1.11.1 in the venv — note the
  mismatch). Either version derives the §2.1 path; verify against §2.3 after pinning.
- `Wallet.version` already means the 1-vs-2 address-path shape (`main/models.py:173`).
  Do **not** overload it for identity versioning; add `identity_version`.
