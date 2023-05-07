from patchwork.transfers import rsync
from fabric import task
from fabric.connection import Connection
from dotenv import dotenv_values


config = dotenv_values(".env")
hosts = [ 'root@' + config['SERVER_IP'] ]
project = "watchtower"


@task
def chipnet(ctx):
    server = config['CHIPNET_SERVER']
    ctx.config.network = 'chipnet'
    user = server.split('@')[0]
    host = server.split('@')[1]
    ctx.config.run.env['conn'] = Connection(
        host,
        user=user,
        connect_kwargs = { 'key_filename': config['SERVER_SSH_KEY'] }
    )


@task
def mainnet(ctx):
    server = config['MAINNET_SERVER']
    ctx.config.network = 'mainnet'
    user = server.split('@')[0]
    host = server.split('@')[1]
    ctx.config.run.env['conn'] = Connection(
        host,
        user=user
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
        f'/home/ubuntu/{project}',
        exclude=[
            '.venv',
            '.git',
            '/static',
            '.DS_Store',
            '.env',
            '__pycache__',
            '*.pyc',
            '*.log',
            '*.pid'
        ]
    )
    with conn.cd(f'/home/ubuntu/{project}'):
        conn.run(f'sudo cp compose/.env_{ctx.config.network} .env')


@task
def build(ctx):
    conn = ctx.config.run.env['conn']
    with conn.cd(f'/home/ubuntu/{project}'):
        conn.run(f'sudo docker-compose -f compose/{ctx.config.network}.yml build')


@task
def up(ctx):
    conn = ctx.config.run.env['conn']
    with conn.cd(f'/home/ubuntu/{project}'):
        conn.run(f'sudo docker-compose -f compose/{ctx.config.network}.yml up -d')


@task
def down(ctx):
    conn = ctx.config.run.env['conn']
    with conn.cd(f'/home/ubuntu/{project}'):
        conn.run(f'sudo docker-compose -f compose/{ctx.config.network}.yml down')


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
    with conn.cd(f'/home/ubuntu/{project}/compose'):
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
    with conn.cd(f'/home/ubuntu/{project}'):
        conn.run(f'sudo docker-compose -f compose/{ctx.config.network}.yml logs  -f web')


@task
def reports(ctx):
    conn = ctx.config.run.env['conn']
    with conn.cd(f'/home/ubuntu/{project}'):
        conn.run(f'sudo docker-compose -f compose/{ctx.config.network}.yml exec -T web python manage.py reports -p paytaca')

