from patchwork.transfers import rsync
from fabric import task
import os

hosts = [
    #'root@' + os.environ['WATCHTOWER_SERVER_IP']
    'root@95.217.29.212'
]


@task(hosts=hosts)
def sync(c):
    rsync(
        c,
        '.',
        '/root/code',
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
    with c.cd('/root/code'):
        c.run('docker-compose -f compose/prod.yml build')


@task(hosts=hosts)
def up(c):
    with c.cd('/root/code'):
        c.run('docker-compose -f compose/prod.yml up -d')


@task(hosts=hosts)
def down(c):
    with c.cd('/root/code'):
        c.run('docker-compose -f compose/prod.yml down')


@task(hosts=hosts)
def deploy(c):
    sync(c)
    build(c)
    down(c)
    up(c)


@task(hosts=hosts)
def logs(c):
    with c.cd(f'/root/code'):
        c.run(f'docker-compose -p code -f compose/prod.yml logs  -f web')
