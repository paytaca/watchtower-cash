from patchwork.transfers import rsync
from fabric import task
import os

hosts = [
    #'root@' + os.environ['WATCHTOWER_SERVER_IP']
    'root@95.217.29.212'
]

config = dotenv_values(".env")
hosts = [ 'root@' + config['SERVER_IP'] ]
project = "watchtower"

@task(hosts=hosts)
def sync(c):
    rsync(
        c,
        '.',
        f'/root/{project}',
        exclude=[
            '.venv',
            '.git',
            'static',
            '.DS_Store',
            '.env',
            '__pycache__',
            '*.pyc',
            '*.log',
            '*.pid'
        ]
    )


@task(hosts=hosts)
def build(c):
    with c.cd(f'/root/{project}'):
        c.run('docker-compose -f compose/staging/setup.yml build')


@task(hosts=hosts)
def up(c):
    with c.cd(f'/root/{project}'):
        c.run('docker-compose -f compose/staging/setup.yml up -d')


@task(hosts=hosts)
def down(c):
    with c.cd(f'/root/{project}'):
        c.run('docker-compose -f compose/staging/setup.yml down')


@task(hosts=hosts)
def deploy(c):
    sync(c)
    build(c)
    down(c)
    up(c)


@task(hosts=hosts)
def nginx(c):
    sync(c)
    with c.cd(f'/root/{project}/compose'):
        nginx_conf = f"/etc/nginx/sites-available/{project}"
        nginx_slink = f"/etc/nginx/sites-enabled/{project}"

        c.run(f'sudo rm {nginx_conf}')
        c.run(f'sudo rm {nginx_slink}')

        c.run(f'sudo cat nginx.conf > {nginx_conf}')
        c.run(f'sudo ln -s {nginx_conf} {nginx_slink}')

        c.run('sudo service nginx restart')


@task(hosts=hosts)
def logs(c):
    with c.cd(f'/root/{project}'):
        c.run(f'docker-compose -p {project} -f compose/staging/setup.yml logs  -f backend')
