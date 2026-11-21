from patchwork.transfers import rsync
from fabric import task
from fabric.connection import Connection
from dotenv import dotenv_values
from pathlib import Path
import re
import shlex


def get_active_branch_name():
    head_dir = Path(".") / ".git" / "HEAD"
    with head_dir.open("r") as f: content = f.read().splitlines()
    for line in content:
        if line[0:4] == "ref:":
            return line.partition("refs/heads/")[2]


config = dotenv_values(".env")
project = "watchtower"

NETWORK_ENV_FILES = {
    "mainnet": "compose/.env_mainnet",
    "chipnet": "compose/.env_chipnet",
}

# mainnet.yml calls the application service "web"; chipnet.yml calls it "backend".
NETWORK_SERVICES = {
    "mainnet": "web",
    "chipnet": "backend",
}

SIGNING_SECRETS = ("SECRET_KEY", "JWT_SIGNING_KEY")

# Must match internal_services/client.py and the Node service auth middleware.
SERVICE_TOKENS = (
    "ADDRESS_JS_AUTH_TOKEN",
    "CTS_JS_AUTH_TOKEN",
    "MULTISIG_JS_AUTH_TOKEN",
    "ANYHEDGE_JS_AUTH_TOKEN",
    "STABLEHEDGE_JS_AUTH_TOKEN",
)

CREDENTIALS_DIR = "/var/opt/watchtower/credentials"
CREDENTIALS_SOURCE = Path("compose/credentials")
CREDENTIALS_STAGING = "/tmp/watchtower-credentials"
PRIVATE_PROOFS_DIR = "/var/opt/watchtower/private-p2p-proofs"
RUNTIME_DIRS = (
    "/var/www/images",
    "/var/opt/watchtower/media",
)


def network_env_file(ctx):
    return NETWORK_ENV_FILES[ctx.config.network]


def compose_env_file(ctx):
    return f"{ctx.config.project_dir}/{network_env_file(ctx)}"


def compose(ctx, command):
    conn = ctx.config.run.env["conn"]
    compose_file = f"compose/{ctx.config.network}.yml"
    with conn.cd(ctx.config.project_dir):
        conn.run(
            f"docker-compose -f {compose_file} "
            f"--env-file {compose_env_file(ctx)} {command}"
        )


def check_env(ctx):
    """Fail before uploading anything when the branch's required secrets are missing."""
    values = dotenv_values(network_env_file(ctx))
    problems = []

    for name in SIGNING_SECRETS:
        value = (values.get(name) or "").strip()
        if len(value) < 50 or len(set(value)) < 5:
            problems.append(
                f"{name} must be a randomly generated secret of at least 50 characters"
            )

    for name in SERVICE_TOKENS:
        value = (values.get(name) or "").strip()
        if not re.fullmatch(r"[A-Za-z0-9_-]{43,}", value) or len(set(value)) < 5:
            problems.append(
                f"{name} must be a randomly generated URL-safe token "
                "of at least 43 characters"
            )

    if problems:
        raise ValueError(
            f"Invalid deployment environment in {network_env_file(ctx)}:\n  - "
            + "\n  - ".join(problems)
        )


@task
def chipnet(ctx):
    ctx.config.network = 'chipnet'
    ctx.config.project_dir = f'/root/{project}'
    ctx.config.run.env['conn'] = Connection(
        config['CHIPNET_SERVER_HOST'],
        user=config['CHIPNET_SERVER_USER']
    )


@task
def mainnet(ctx):
    branch = get_active_branch_name()
    # if branch == 'master':
    ctx.config.network = 'mainnet'
    ctx.config.project_dir = f'/root/{project}'
    ctx.config.run.env['conn'] = Connection(
        config['MAINNET_SERVER_HOST'],
        user=config['MAINNET_SERVER_USER']
    )
    # else:
    #     print(f'\nAborted: {branch} branch is not allowed to access mainnet server!\n')

@task
def uname(ctx):
    if 'network' not in ctx.config.keys(): return
    conn = ctx.config.run.env['conn']
    conn.run('uname -a')


@task
def sync(ctx):
    if 'network' not in ctx.config.keys(): return
    conn = ctx.config.run.env['conn']
    rsync(
        conn,
        '.',
        ctx.config.project_dir,
        exclude=[
            '.venv',
            '.git',
            '.env',
            '/static',
            'media',
            'images',
            'private-p2p-proofs',
            'node_modules',
            'compose/credentials',
            'compose/firebase-admin-credentials.json',
            'compose/APNS_AuthKey.p8',
            '.DS_Store',
            '__pycache__',
            '*.pyc',
            '*.log',
            '*.pid'
        ]
    )


@task
def provision(ctx):
    """Create the non-root runtime paths and install the network's credentials."""
    if 'network' not in ctx.config.keys(): return
    source = CREDENTIALS_SOURCE / ctx.config.network
    if not source.is_dir() or not any(source.iterdir()):
        raise RuntimeError(
            f'No credential files found in {source}; '
            'add the network credentials before deploying'
        )

    conn = ctx.config.run.env['conn']

    conn.run(
        f'sudo install -d -o 10001 -g 10001 -m 0750 {CREDENTIALS_DIR} {PRIVATE_PROOFS_DIR}'
    )
    conn.run(
        'sudo install -d -o 10001 -g 10001 -m 0755 ' + ' '.join(RUNTIME_DIRS)
    )

    # Stage outside the project directory, then mirror the whole folder so
    # removed or new credential files are reflected on the server.
    conn.run(f'rm -rf {CREDENTIALS_STAGING}')
    conn.run(f'install -d -m 0700 {CREDENTIALS_STAGING}')
    rsync(
        conn,
        str(source) + '/',
        CREDENTIALS_STAGING,
        exclude=['.DS_Store'],
    )
    # Keep live credentials while transferring replacements; prune orphans only
    # after the transfer. Delayed updates also avoid partially written files.
    conn.run(
        'sudo rsync -a --delay-updates --delete-delay '
        '--chown=10001:10001 --chmod=D0750,F0400 '
        f'{CREDENTIALS_STAGING}/ {CREDENTIALS_DIR}/'
    )
    conn.run(f'rm -rf {CREDENTIALS_STAGING}')


@task
def check_env_file(ctx):
    if 'network' not in ctx.config.keys(): return
    check_env(ctx)
    print(f'{network_env_file(ctx)} contains the required signing keys and service tokens.')


@task
def build(ctx):
    if 'network' not in ctx.config.keys(): return
    compose(ctx, 'build')


@task
def up(ctx):
    if 'network' not in ctx.config.keys(): return
    compose(ctx, 'up -d')


@task
def down(ctx):
    if 'network' not in ctx.config.keys(): return
    compose(ctx, 'down --remove-orphans')


@task
def deploy(ctx):
    if 'network' not in ctx.config.keys(): return
    check_env(ctx)
    sync(ctx)
    provision(ctx)
    build(ctx)
    down(ctx)
    up(ctx)
    clear_caches(ctx)


@task
def nginx(ctx):
    if 'network' not in ctx.config.keys(): return
    sync(ctx)
    conn = ctx.config.run.env['conn']
    with conn.cd(f'{ctx.config.project_dir}/compose'):
        nginx_conf = f"/etc/nginx/sites-available/{project}"
        nginx_slink = f"/etc/nginx/sites-enabled/{project}"

        try:
            conn.run(f'sudo rm {nginx_conf}')
            conn.run(f'sudo rm {nginx_slink}')
        except:
            pass

        conn.run(f'sudo cat nginx.conf > {nginx_conf}')
        conn.run(f'sudo ln -s {nginx_conf} {nginx_slink}')

        conn.run('sudo service nginx restart')


@task
def clear_caches(ctx):
    if 'network' not in ctx.config.keys(): return
    service = NETWORK_SERVICES[ctx.config.network]
    compose(ctx, f'exec -T {service} python manage.py clear_caches')


@task
def logs(ctx):
    if 'network' not in ctx.config.keys(): return
    service = NETWORK_SERVICES[ctx.config.network]
    compose(ctx, f'logs -f {service}')


@task
def reports(ctx):
    if 'network' not in ctx.config.keys(): return
    service = NETWORK_SERVICES[ctx.config.network]
    compose(ctx, f'exec -T {service} python manage.py reports -p paytaca')

@task
def check_tx(ctx, txid):
    if 'network' not in ctx.config.keys(): return
    service = NETWORK_SERVICES[ctx.config.network]
    compose(ctx, f'exec -T {service} python manage.py tx_fiat_amounts -t {shlex.quote(txid)} -c php')
