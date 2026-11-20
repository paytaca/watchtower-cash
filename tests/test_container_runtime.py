"""Opt-in runtime test of the Dockerfile's actual non-root setup.

Uses an existing local dependency image; no application settings, databases,
credentials, or signing functions are loaded. No repository-wide build context
is sent to Docker.
"""
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]


@unittest.skipUnless(os.environ.get('RUN_CONTAINER_RUNTIME_TESTS') == '1', 'requires local Docker')
class ContainerRuntimeTests(unittest.TestCase):
    def test_compose_security_and_storage_settings_resolve(self):
        for filename, services in [
            ('compose/mainnet.yml', ['web']),
            ('compose/chipnet.yml', ['backend']),
            ('docker-compose.yml', ['backend', 'test']),
        ]:
            with self.subTest(compose=filename), tempfile.TemporaryDirectory(prefix='watchtower-compose-test-') as directory:
                context = Path(directory)
                source = (ROOT / filename).read_text()
                # Substitute only env-file references; never read real env files.
                source = source.replace('/root/watchtower/compose/.env_mainnet', './synthetic.env')
                source = source.replace('/root/watchtower/compose/.env_chipnet', './synthetic.env')
                source = source.replace('.env_dev', './synthetic.env')
                (context / 'synthetic.env').write_text('SYNTHETIC_CONFIG_ONLY=1\n')
                config = context / 'compose.yml'
                config.write_text(source)
                result = subprocess.run([
                    'docker', 'compose', '--env-file', str(context / 'synthetic.env'),
                    '-f', str(config), 'config', '--format', 'json',
                ], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, timeout=30)
                self.assertEqual(result.returncode, 0, result.stderr)
                resolved = json.loads(result.stdout)
                for name in services:
                    service = resolved['services'][name]
                    self.assertEqual(service['cap_drop'], ['ALL'])
                    self.assertIn('no-new-privileges:true', service['security_opt'])
                    mounts = {volume['target']: volume for volume in service['volumes']}
                    for path in ['/code/media', '/code/private-p2p-proofs', '/images']:
                        self.assertFalse(mounts[path].get('read_only', False))
                    if filename.startswith('compose/'):
                        self.assertEqual(service['user'], '10001:10001')
                        self.assertTrue(mounts['/run/watchtower-credentials']['read_only'])
                    else:
                        self.assertEqual(mounts['/code/static']['type'], 'volume')

    def test_nonroot_permissions_supervisor_and_entrypoint(self):
        with tempfile.TemporaryDirectory(prefix='watchtower-nonroot-test-') as directory:
            context = Path(directory)
            dockerfile = (ROOT / 'Dockerfile').read_text()
            runtime = dockerfile[dockerfile.index('ENV LC_ALL='):dockerfile.index('ENTRYPOINT')]
            (context / 'Dockerfile').write_text(
                'FROM watchtower-cash-backend:latest\nUSER root\n'
                'RUN printf synthetic > /code/runtime-canary\n'
                'COPY supervisor-configs /tmp/supervisor-configs\n'
                'COPY entrypoint.sh /tmp/entrypoint-under-test.sh\n'
                'COPY runtime_probe.py /tmp/runtime_probe.py\n' + runtime +
                '\nENTRYPOINT ["python", "/tmp/runtime_probe.py"]\n'
            )
            configs = context / 'supervisor-configs'
            configs.mkdir()
            for path in [ROOT / 'supervisord.conf', ROOT / 'supervisord-mainnet.conf', *(ROOT / 'supervisor').glob('*.conf')]:
                (configs / path.name).write_text(path.read_text())
            (context / 'entrypoint.sh').write_text((ROOT / 'entrypoint.sh').read_text())
            (context / 'runtime_probe.py').write_text(RUNTIME_PROBE)
            image = None
            try:
                built = subprocess.run([
                    'docker', 'build', '--network=none', '--pull=false',
                    '--iidfile', str(context / 'image-id'), str(context),
                ], stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, timeout=180)
                self.assertEqual(built.returncode, 0, built.stdout)
                image = (context / 'image-id').read_text().strip()
                result = subprocess.run([
                    'docker', 'run', '--rm', '--network=none', '--cap-drop=ALL',
                    '--security-opt=no-new-privileges:true', image,
                ], stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, timeout=60)
                self.assertEqual(result.returncode, 0, result.stdout)
                print(result.stdout)
            finally:
                if image:
                    subprocess.run(['docker', 'image', 'rm', image], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=30)


RUNTIME_PROBE = r'''
import configparser
import os
from pathlib import Path
import socket
import subprocess
import tempfile
import time
from supervisor.options import ServerOptions

assert os.getuid() == os.getgid() == 10001
assert os.environ['HOME'] == '/home/watchtower'
status = Path('/proc/self/status').read_text()
assert 'CapEff:\t0000000000000000' in status
assert 'NoNewPrivs:\t1' in status
for path in ['/code/runtime-canary', '/code/unauthorized-source.py', '/root/unauthorized']:
    try:
        with open(path, 'w') as handle:
            handle.write('should not succeed')
    except PermissionError:
        pass
    else:
        raise AssertionError('Unexpected write access: ' + path)
for directory in ['/home/watchtower', '/run/watchtower', '/var/lib/watchtower', '/code/static', '/code/media', '/code/private-p2p-proofs', '/images']:
    probe = Path(directory) / 'runtime-permission-probe'
    probe.write_text('synthetic')
    probe.unlink()
with socket.socket() as server:
    server.bind(('127.0.0.1', 0))
print('PASS: non-root UID, zero capabilities, no-new-privileges, protected code, writable runtime paths and sockets')

os.environ['CTS_APP_ENV'] = 'synthetic'
for path in Path('/tmp/supervisor-configs').glob('*.conf'):
    options = ServerOptions()
    options.realize(['-c', str(path)])
print('PASS: all production/development Supervisor configurations parse as non-root')

config = configparser.ConfigParser(interpolation=None)
config.read('/tmp/supervisor-configs/supervisord-mainnet.conf')
for section in config.sections():
    if section.startswith('program:'):
        config.remove_section(section)
config['program:runtime_probe'] = {
    'command': 'python -c "import time; time.sleep(30)"', 'startsecs': '0',
    'stdout_logfile': '/dev/stdout', 'stdout_logfile_maxbytes': '0',
    'stderr_logfile': '/dev/stderr', 'stderr_logfile_maxbytes': '0',
}
probe_config = '/tmp/supervisor-runtime-probe.conf'
with open(probe_config, 'w') as handle:
    config.write(handle)
process = subprocess.Popen(['supervisord', '-c', probe_config, '--nodaemon'], stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
try:
    for _ in range(100):
        if Path('/run/watchtower/supervisor.sock').exists() or process.poll() is not None:
            break
        time.sleep(0.1)
    check = subprocess.run(['supervisorctl', '-c', probe_config, 'status'], stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    assert check.returncode == 0 and 'RUNNING' in check.stdout, check.stdout
    subprocess.run(['supervisorctl', '-c', probe_config, 'shutdown'], check=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    output, _ = process.communicate(timeout=15)
    assert process.returncode == 0, output
finally:
    if process.poll() is None:
        process.kill()
        process.communicate()
print('PASS: Supervisor starts, controls an unprivileged worker, and shuts down through its Unix socket')

with tempfile.TemporaryDirectory() as directory:
    bin_dir = Path(directory)
    wait = bin_dir / 'wait-for-it.sh'
    wait.write_text('#!/bin/sh\nexit 0\n')
    wait.chmod(0o755)
    python = bin_dir / 'python'
    python.write_text('#!/bin/sh\nexit 17\n')
    python.chmod(0o755)
    env = dict(os.environ, PATH=str(bin_dir) + ':' + os.environ['PATH'], POSTGRES_HOST='127.0.0.1', POSTGRES_PORT='5432')
    sentinel = bin_dir / 'should-not-start'
    check = subprocess.run(['sh', '/tmp/entrypoint-under-test.sh', 'touch', str(sentinel)], env=env)
    assert check.returncode == 17 and not sentinel.exists()
    python.write_text('#!/bin/sh\nexit 0\n')
    check = subprocess.run(['sh', '/tmp/entrypoint-under-test.sh', 'id', '-u'], env=env, stdout=subprocess.PIPE, text=True)
    assert check.returncode == 0 and check.stdout.strip() == '10001'
print('PASS: entrypoint fails on migration errors and executes successful startup as UID 10001')
'''
