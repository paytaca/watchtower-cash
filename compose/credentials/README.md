# Runtime credentials

This directory holds deployment credentials, one folder per network:

```text
compose/credentials/
  mainnet/
    firebase-admin-credentials.json
    APNS_AuthKey.p8
  chipnet/
    firebase-admin-credentials.json
    APNS_AuthKey.p8
```

`fab <network> provision` uploads the whole `compose/credentials/<network>/`
folder to `/var/opt/watchtower/credentials` on the deployment host, owned by
UID/GID 10001 and mounted read-only at `/run/watchtower-credentials`.

The folders are gitignored. Never add the contents to `.dockerignore`-included
paths or commit them. APNs is optional: omit `APNS_AuthKey.p8` when token
authentication is disabled.
