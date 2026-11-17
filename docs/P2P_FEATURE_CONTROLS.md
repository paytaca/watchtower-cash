# Server-side P2P feature controls

## Full HTTP maintenance pause

Deploy this patch to every API instance and apply migrations (including
`0244_featurecontrol_p2p_maintenance`). In Django admin → Ramp P2P → Feature
controls, create **P2P maintenance (enabled = paused)** (`P2P_MAINTENANCE`) and
check **Is enabled**. This control deliberately means the opposite of the
individual feature permissions: enabled maintenance means **P2P is paused**.
A missing or disabled maintenance record leaves the global pause off. The
migration updates available choices only; it does not activate maintenance or
create records automatically.

During maintenance, every HTTP route under `/api/ramp-p2p/` returns HTTP 503 with
`code: "p2p_maintenance"` before view execution or authentication. The only
exceptions are `feature-control/` and `feature-toggles/`, which remain readable
so clients can see `P2P_MAINTENANCE: true`. Responses are marked `no-store`.
The pause covers public/router-format routes and cash-in aliases as well as
authenticated APIs. It overrides individually enabled feature controls.

This blocks order lists/details, contract reads/generation, new trades, profile
changes, cancellation, appeals, payment handling, webhooks and settlement
verification through those HTTP routes. Django admin, management/audit commands,
authentication endpoints outside that namespace and background blockchain
listeners are not blocked. Arrange admin/support handling for existing funded
orders while their normal API screens are unavailable.

The inspected frontend needs a successful order-detail request to initialize a
fresh order screen. This pause prevents that fetch. **It does not remotely clear
an already-open screen or cached contract data**, close existing WebSockets, or
stop a wallet broadcasting a transaction. The existing frontend calls
`pending-escrow` after sending BCH, so blocking that request alone cannot prevent
funding. A frontend maintenance check before signing/sending is still required
to cover already-open funding screens. Notify users not to fund existing orders.

Verify on production that an order-detail request returns 503 with the
maintenance code and the feature endpoint still returns the enabled flag. Until
all instances run this patch and that behavior is verified, treat the API as
active. Uncheck **Is enabled** on this record to lift the global pause. Individual
permissions below still apply afterward; lifting maintenance does not enable
them automatically.

## Individual operation permissions

After deploying this patch to every API instance, the existing Django admin
Feature controls apply to the API handlers as well as any frontend controls.
When full maintenance is off, each protected request checks the database directly.
Disabled **or missing**
records return HTTP 503 with `code: "p2p_feature_disabled"` and the feature name,
before the handler performs business queries, writes, notifications or task
submission. Existing authentication and permission checks still run first.

| Control | Protected operations |
| --- | --- |
| `ORDER_CREATE` | New P2P orders, including cash-in orders |
| `ORDER_ESCROW` | Contract creation/regeneration, including `force`, and escrow initiation |
| `AD_CREATE` | New ads |
| `AD_UPDATE` | Ad updates, including making an ad public |
| `AD_SHARE_LINKS` | Ad share landing page |

To pause new trading, create these records if absent and uncheck **Is enabled**
in Django admin → Ramp P2P → Feature controls. Changes take effect on the next
protected request without an API restart. Missing records intentionally fail
closed; create and explicitly enable records for features you intend to permit.
No new schema changes are required for these five existing permissions.

Order/ad viewing, ad deletion, order cancellation, appeals, payment handling,
and transaction verification retain their existing behavior and permissions.
Escrow verification remains available to record funding already broadcast;
release/refund verification remains available for existing funded orders **when
full maintenance is off**. These five permissions alone pause only the listed operations.
Peer/arbiter key and address updates are not controlled by these five flags.

Keep frontend maintenance controls disabled as well. The server cannot prevent
someone funding a previously known address or broadcasting a signed transaction
directly to the blockchain. Requests already executing and previously queued
tasks are not canceled when a toggle changes. Review existing contracts and
funded orders separately before approving settlement.

Run the API guard regression tests using synthetic test data:

```bash
docker compose run --rm --entrypoint python test -m pytest \
  rampp2p/test_feature_control.py rampp2p/test_maintenance.py -v -o addopts=""
```

The tests exercise actual URL routing and database feature records. Caller
authentication is substituted so the tests focus on enforcement and prove that
blocked handlers execute only control lookups, with no business queries or
mutations. They also cover missing records, next-request toggle changes,
independent controls, enabled-handler delegation, and availability of reads,
cancellation authorization, settlement validation and feature-control reads.
The maintenance tests cover every registered P2P HTTP callback, both public and
authenticated routes, enabled/missing/disabled maintenance, and restoration of
normal authentication when the global pause is lifted.
