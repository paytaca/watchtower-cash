from patchwork.transfers import rsync
from fabric import task
from fabric.connection import Connection
from dotenv import dotenv_values
from pathlib import Path


def get_active_branch_name():
    head_dir = Path(".") / ".git" / "HEAD"
    with head_dir.open("r") as f: content = f.read().splitlines()
    for line in content:
        if line[0:4] == "ref:":
            return line.partition("refs/heads/")[2]


config = dotenv_values(".env")
project = "watchtower"


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
            '/static',
            '.DS_Store',
            '__pycache__',
            '*.pyc',
            '*.log',
            '*.pid'
        ]
    )
    with conn.cd(ctx.config.project_dir):
        conn.run(f'cat compose/.env_{ctx.config.network} >> .env')


@task
def build(ctx):
    if 'network' not in ctx.config.keys(): return
    conn = ctx.config.run.env['conn']
    with conn.cd(ctx.config.project_dir):
        conn.run(f'docker-compose -f compose/{ctx.config.network}.yml --env-file {ctx.config.project_dir}/.env build')


@task
def up(ctx):
    if 'network' not in ctx.config.keys(): return
    conn = ctx.config.run.env['conn']
    with conn.cd(ctx.config.project_dir):
        conn.run(f'docker-compose -f compose/{ctx.config.network}.yml --env-file {ctx.config.project_dir}/.env up -d')


@task
def down(ctx):
    if 'network' not in ctx.config.keys(): return
    conn = ctx.config.run.env['conn']
    with conn.cd(ctx.config.project_dir):
        conn.run(f'docker-compose -f compose/{ctx.config.network}.yml --env-file {ctx.config.project_dir}/.env down --remove-orphans')


@task
def deploy(ctx):
    if 'network' not in ctx.config.keys(): return
    sync(ctx)
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
    conn = ctx.config.run.env['conn']
    with conn.cd(ctx.config.project_dir):
        conn.run(f'docker-compose -f compose/{ctx.config.network}.yml --env-file {ctx.config.project_dir}/.env exec -T web python manage.py clear_caches')


@task
def logs(ctx):
    if 'network' not in ctx.config.keys(): return
    conn = ctx.config.run.env['conn']
    with conn.cd(ctx.config.project_dir):
        conn.run(f'docker-compose -f compose/{ctx.config.network}.yml --env-file {ctx.config.project_dir}/.env logs  -f web')


@task
def reports(ctx):
    if 'network' not in ctx.config.keys(): return
    conn = ctx.config.run.env['conn']
    with conn.cd(ctx.config.project_dir):
        conn.run(f'docker-compose -f compose/{ctx.config.network}.yml --env-file {ctx.config.project_dir}/.env exec -T web python manage.py reports -p paytaca')

@task
def check_tx(ctx, txid):
    if 'network' not in ctx.config.keys(): return
    conn = ctx.config.run.env['conn']
    with conn.cd(ctx.config.project_dir):
        conn.run(f'docker-compose -f compose/{ctx.config.network}.yml --env-file {ctx.config.project_dir}/.env exec -T web python manage.py tx_fiat_amounts -t {txid} -c php') 