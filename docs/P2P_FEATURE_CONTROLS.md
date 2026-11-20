# P2P feature controls

P2P feature controls determine which HTTP operations are available. Their values
are stored in `FeatureControl` and checked on each request.

## Controls

| Control | Behavior when enabled |
| --- | --- |
| `P2P_MAINTENANCE` | Pauses P2P HTTP operations, except feature-state reads |
| `ORDER_CREATE` | Allows order creation, including cash-in orders |
| `ORDER_ESCROW` | Allows contract creation/regeneration and escrow initiation |
| `AD_CREATE` | Allows ad creation |
| `AD_UPDATE` | Allows ad updates |
| `AD_SHARE_LINKS` | Allows ad share landing pages |

`P2P_MAINTENANCE` takes precedence over the individual controls. A missing or
disabled maintenance control leaves the global pause off. Individual operation
controls must exist and be enabled for their operations to be available.

Individual controls govern the operations listed above. Other P2P operations
retain their normal behavior when maintenance is off. These controls apply to
HTTP requests; background workers and blockchain activity are separate.

## Feature state and API responses

Clients can read feature state from `/api/ramp-p2p/feature-control/` or
`/api/ramp-p2p/feature-toggles/`. These endpoints remain available during
maintenance.

A maintenance pause returns HTTP 503 with `code: "p2p_maintenance"`. An unavailable
individual operation returns HTTP 503 with `code: "p2p_feature_disabled"` and the
control name. These responses use `Cache-Control: no-store`.

Configuration changes take effect on subsequent requests without restarting the
API. Normal authentication and permissions continue to apply when an operation
is available.

## Tests

`rampp2p/test_feature_control.py` covers individual controls and
`rampp2p/test_maintenance.py` covers the maintenance pause and feature-state reads.
