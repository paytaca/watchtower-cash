# P2P login fix and incident audit

The login fix binds peer and arbiter signatures to their registered public keys.
It does not invalidate previously issued tokens or repair account keys changed
before deployment. The steps below are explicit operator actions; no migration
or application startup hook runs them automatically.

## Before deployment

Preserve relevant access logs and database evidence. Check all peer and arbiter
public keys using this read-only command on the deployment host. It prints only
the account type and ID for invalid keys, never tokens or private keys:

```bash
docker compose exec -T backend python manage.py shell <<'PY'
from rampp2p.models import Peer, Arbiter
from rampp2p.order_audit import canonical_key

invalid = 0
for model in (Peer, Arbiter):
    for account in model.objects.only('id', 'public_key').iterator():
        try:
            canonical_key(account.public_key)
        except ValueError:
            invalid += 1
            print(model.__name__, account.pk, 'INVALID_REGISTERED_KEY')
print('Invalid account keys:', invalid)
PY
```

This check requires the updated `order_audit` code to be available on the host;
run it from the new image before enabling login traffic if necessary. A valid
curve point is not proof of ownership: compare affected accounts with trusted
pre-incident records and the owner's independently verified wallet key/address.
Accounts with missing, malformed, or attacker-replaced keys need verified
recovery. Do not bypass key checks or ask users to re-register over existing
accounts; existing wallet hashes and usernames are unique.

## Deploy and revoke old credentials

Coordinate a short P2P maintenance window so old sessions cannot race profile
updates or create orders while remediation runs. Deploy the login fix, verify
affected profiles, then revoke existing peer/arbiter credentials before reopening
P2P access. Also restrict token-only public-key/address changes in the companion
patch; the login fix alone does not prevent persistence through stolen tokens.

`AuthToken` is shared across applications and has no application discriminator.
The following selects tokens by membership in Peer/Arbiter, including disabled
accounts. Expiring these records also logs out any main-wallet session sharing
the same wallet hash. Users must authenticate again. Both scripts print the
per-wallet token counts before any revocation, so operators can review the
account scope even for large batches. Keep this output with the incident record;
it contains wallet hashes, but never bearer tokens. Review this scope first:

```bash
docker compose exec -T backend python manage.py shell <<'PY'
from django.db.models import Count, Q
from authentication.models import AuthToken
from rampp2p.models import Peer, Arbiter

tokens = AuthToken.objects.filter(
    Q(wallet_hash__in=Peer.objects.values('wallet_hash')) |
    Q(wallet_hash__in=Arbiter.objects.values('wallet_hash'))
)
print('Token records selected for revocation:', tokens.count())
print('wallet_hash\ttoken_records')
for row in tokens.values('wallet_hash').annotate(token_count=Count('pk')).order_by('wallet_hash'):
    print(row['wallet_hash'], row['token_count'], sep='\t')
PY
```

Once ready to revoke, explicitly run:

```bash
docker compose exec -T backend python manage.py shell <<'PY'
from django.db.models import Count, Q
from django.utils import timezone
from authentication.models import AuthToken
from rampp2p.models import Peer, Arbiter

tokens = AuthToken.objects.filter(
    Q(wallet_hash__in=Peer.objects.values('wallet_hash')) |
    Q(wallet_hash__in=Arbiter.objects.values('wallet_hash'))
)
print('Token records selected for revocation:', tokens.count())
print('wallet_hash\ttoken_records')
for row in tokens.values('wallet_hash').annotate(token_count=Count('pk')).order_by('wallet_hash'):
    print(row['wallet_hash'], row['token_count'], sep='\t')
count = tokens.update(key_expires_at=timezone.now(), nonce=None, nonce_expires_at=None)
print('Revoked token records and cleared pending challenges:', count)
PY
```

This retains token records for investigation. The existing OTP flow generates a
new token when the old token is expired. Test both rejection of old tokens and
successful reauthentication. Do not run the revocation automatically on every
restart or deployment.

## Audit and verify

Run against production data after the command has been tested against a test
database. Export all selected orders first, including those without flags:

```bash
docker compose exec -T backend python manage.py audit_p2p_orders \
  --days 7 --format json > p2p-order-audit.json
```

Flags are investigation leads, not proof of abuse. Profile comparisons use
current database values. Missing transaction records do not establish that a
contract is unfunded; independently check the chain before canceling orders.
Keep exports private. This audit does not cancel orders or move funds.

Run the regression and database-backed command tests:

```bash
docker compose run --rm --entrypoint python test -m pytest \
  authentication/tests.py rampp2p/test_order_audit.py \
  rampp2p/test_order_audit_command.py -v -o addopts=""
```

The database-backed tests require the configured PostgreSQL service and test
database creation privileges; all test records are synthetic. Notification
side effects are suppressed while creating fixtures.
