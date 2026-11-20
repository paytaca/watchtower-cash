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

Both paths are overridden by `compose/mainnet.yml` and `compose/chipnet.yml`.
The build context intentionally excludes `*.p8`, service-account JSON, env
files, and private uploads.

## Writable runtime paths

Supervisor and Celery Beat write under `/var/run/watchtower`:

- `supervisord.pid`
- `supervisord.log`
- `supervisor.sock`
- `celerybeat-schedule`

Django's static, media, and token-image directories are the only application
source-tree paths intentionally writable by UID/GID 10001. Python bytecode
writing is disabled in the image.

## Checks

Static configuration checks always run:

```bash
python -m unittest tests.test_container_runtime -v
```

Runtime checks are opt-in and require a locally built image:

```bash
RUN_CONTAINER_RUNTIME_TESTS=1 \
WATCHTOWER_TEST_IMAGE=watchtower_web:latest \
python -m unittest tests.test_container_runtime -v
```
