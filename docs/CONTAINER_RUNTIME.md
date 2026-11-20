# Container runtime and credential layout

The application image runs as **UID/GID 10001**. Production Compose also
enforces `user: "10001:10001"`, drops all Linux capabilities, and enables
`no-new-privileges`.

## Host directories

Provision these paths on the Docker host before starting the service:

| Host path | Container path | Required access |
|---|---|---|
| `/var/opt/watchtower/credentials` | `/run/watchtower-credentials` | UID/GID 10001 read |
| `/var/www/images` | `/images` | UID/GID 10001 write |
| `/var/opt/watchtower/media` | `/code/media` | UID/GID 10001 write |
| `/var/opt/watchtower/private-p2p-proofs` | `/code/private-p2p-proofs` | UID/GID 10001 write |

The credentials directory must contain, as configured:

- `firebase-admin-credentials.json`
- `APNS_AuthKey.p8` when APNs token authentication is enabled

The Firebase path is set by `compose/mainnet.yml` and `compose/chipnet.yml`.
They also set `APNS_AUTH_KEY_PATH` to the mounted key by default; override that
variable only when the key has a different filename. When APNs token
authentication is enabled, provision `APNS_AuthKey.p8` in the credentials
directory. Omit APNs configuration when it is unused.
The build context intentionally excludes `*.p8`, service-account JSON, env
files, and private uploads.

## Writable runtime paths

Supervisor writes `supervisord.pid`, `supervisor.sock`, and child-process
runtime files under `/run/watchtower`. Supervisor's activity log goes to
stdout. Celery Beat writes its schedule under
`/var/lib/watchtower/celerybeat-schedule` and its PID under
`/run/watchtower/celerybeat.pid`.

Django's static, media, and token-image directories are the only application
source-tree paths intentionally writable by UID/GID 10001. Python bytecode
writing is disabled in the image.

## Checks

Runtime validation uses an existing local dependency image and synthetic configuration:

```bash
RUN_CONTAINER_RUNTIME_TESTS=1 python -m unittest tests.test_container_runtime -v
```

This uses `watchtower-cash-backend:latest` as the dependency image. Set
`WATCHTOWER_TEST_BASE_IMAGE` to select another local dependency image that does
not already contain the final non-root setup. It does not start Watchtower or
connect to a database.

To check an actual freshly built application image as well:

```bash
RUN_BUILT_IMAGE_RUNTIME_TESTS=1 \
WATCHTOWER_TEST_IMAGE=watchtower_web:latest \
python -m unittest tests.test_container_runtime -v
```
