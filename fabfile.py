from patchwork.transfers import rsync
from fabric import task
from fabric.connection import Connection
from dotenv import dotenv_values


config = dotenv_values(".env")
project = "watchtower"


@task
def chipnet(ctx):
    ctx.config.network = 'chipnet'
    ctx.config.project_dir = f'/home/ubuntu/{project}'
    ctx.config.run.env['conn'] = Connection(
        config['CHIPNET_SERVER_HOST'],
        user=config['CHIPNET_SERVER_USER'],
        connect_kwargs = { 'key_filename': config['SERVER_SSH_KEY'] }
    )


@task
def mainnet(ctx):
    ctx.config.network = 'mainnet'
    ctx.config.project_dir = f'/root/{project}'
    ctx.config.run.env['conn'] = Connection(
        config['MAINNET_SERVER_HOST'],
        user=config['MAINNET_SERVER_USER']
    )


@task
def uname(ctx):
    conn = ctx.config.run.env['conn']
    conn.run('uname -a')


@task
def sync(ctx):
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
    conn = ctx.config.run.env['conn']
    with conn.cd(ctx.config.project_dir):
        conn.run(f'docker-compose -f compose/{ctx.config.network}.yml --env-file {ctx.config.project_dir}/.env build')


@task
def up(ctx):
    conn = ctx.config.run.env['conn']
    with conn.cd(ctx.config.project_dir):
        conn.run(f'docker-compose -f compose/{ctx.config.network}.yml --env-file {ctx.config.project_dir}/.env up -d')


@task
def down(ctx):
    conn = ctx.config.run.env['conn']
    with conn.cd(ctx.config.project_dir):
        conn.run(f'docker-compose -f compose/{ctx.config.network}.yml --env-file {ctx.config.project_dir}/.env down')


@task
def deploy(ctx):
    sync(ctx)
    build(ctx)
    down(ctx)
    up(ctx)


@task
def nginx(ctx):
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
def logs(ctx):
    conn = ctx.config.run.env['conn']
    with conn.cd(ctx.config.project_dir):
        conn.run(f'docker-compose -f compose/{ctx.config.network}.yml --env-file {ctx.config.project_dir}/.env logs  -f web')


@task
def reports(ctx):
    conn = ctx.config.run.env['conn']
    with conn.cd(ctx.config.project_dir):
        conn.run(f'docker-compose -f compose/{ctx.config.network}.yml --env-file {ctx.config.project_dir}/.env exec -T web python manage.py reports -p paytaca')
