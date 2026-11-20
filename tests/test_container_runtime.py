"""Opt-in runtime test of the Dockerfile's actual non-root setup.

Uses an existing local dependency image; no application settings, databases,
credentials, or signing functions are loaded. No repository-wide build context
is sent to Docker.
"""
import json
import os
from pathlib import Path
import subprocess
import shutil
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]


class ContainerConfigurationTests(unittest.TestCase):
    """Checks that run without Docker so CI cannot silently regress setup."""

    def test_dockerfile_uses_unprivileged_identity(self):
        dockerfile = (ROOT / 'Dockerfile').read_text()
        self.assertIn('groupadd --gid 10001 watchtower', dockerfile)
        self.assertIn('useradd --uid 10001 --gid 10001', dockerfile)
        self.assertGreater(
            dockerfile.rfind('USER 10001:10001'),
            dockerfile.rfind('USER root'),
        )
        self.assertIn('USER 10001:10001', dockerfile)
        self.assertNotIn('sudo', dockerfile)
        self.assertIn('PYTHONDONTWRITEBYTECODE=1', dockerfile)
        self.assertIn('ENV HOME=/home/watchtower', dockerfile)

    def test_dockerfile_writable_paths_are_limited(self):
        dockerfile = (ROOT / 'Dockerfile').read_text()
        install = 'install -d -o 10001 -g 10001 -m 0755'
        self.assertIn(install, dockerfile)
        for path in (
            '/home/watchtower', '/run/watchtower', '/var/lib/watchtower',
            '/code/static', '/code/media', '/code/private-p2p-proofs', '/images',
        ):
            self.assertIn(path, dockerfile)

    def test_supervisor_runtime_paths_are_writable_and_not_tmp(self):
        configs = [ROOT / 'supervisord.conf', ROOT / 'supervisord-mainnet.conf']
        configs.extend(sorted((ROOT / 'supervisor').glob('*.conf')))
        self.assertGreaterEqual(len(configs), 6)
        for path in configs:
            with self.subTest(config=path.name):
                text = path.read_text()
                self.assertNotIn('/tmp', text)
                self.assertIn('/run/watchtower', text)
                if 'celerybeat' in text:
                    self.assertIn(
                        '--schedule=/var/lib/watchtower/celerybeat-schedule', text
                    )
                    self.assertIn(
                        '--pidfile=/run/watchtower/celerybeat.pid', text
                    )

    def test_production_compose_drops_privileges_and_mounts_credentials(self):
        for name in ('compose/mainnet.yml', 'compose/chipnet.yml'):
            with self.subTest(compose=name):
                text = (ROOT / name).read_text()
                self.assertIn('user: "10001:10001"', text)
                self.assertIn('cap_drop:', text)
                self.assertIn('- ALL', text)
                self.assertIn('no-new-privileges:true', text)
                self.assertIn(
                    'APNS_AUTH_KEY_PATH: '
                    '"${APNS_AUTH_KEY_PATH:-/run/watchtower-credentials/APNS_AuthKey.p8}"',
                    text,
                )
                self.assertIn(
                    '/var/opt/watchtower/credentials:/run/watchtower-credentials:ro',
                    text,
                )

    def test_development_compose_drops_privileges(self):
        text = (ROOT / 'docker-compose.yml').read_text()
        self.assertIn('cap_drop:', text)
        self.assertIn('- ALL', text)
        self.assertIn('no-new-privileges:true', text)

    def test_entrypoint_fails_fast_and_waits_strictly(self):
        text = (ROOT / 'entrypoint.sh').read_text()
        self.assertIn('set -eu', text)
        self.assertIn('wait-for-it.sh', text)
        self.assertIn('--strict', text)

    def test_build_context_excludes_secrets(self):
        text = (ROOT / '.dockerignore').read_text()
        for pattern in ('**/.env', '**/.env_*', '**/*.p8', '**/*.pem',
                        '**/*.key', '**/*credentials*.json',
                        '**/*service-account*.json'):
            self.assertIn(pattern, text)


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
            base_image = os.environ.get('WATCHTOWER_TEST_BASE_IMAGE', 'watchtower-cash-backend:latest')
            if not base_image or any(character.isspace() for character in base_image):
                raise ValueError('WATCHTOWER_TEST_BASE_IMAGE must be a local Docker image reference')
            (context / 'Dockerfile').write_text(
                'FROM ' + base_image + '\nUSER root\n'
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


@unittest.skipUnless(
    os.environ.get('RUN_BUILT_IMAGE_RUNTIME_TESTS') == '1',
    'set RUN_BUILT_IMAGE_RUNTIME_TESTS=1 to check a freshly built application image',
)
class BuiltImageRuntimeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if not shutil.which('docker'):
            raise unittest.SkipTest('Docker CLI is unavailable')
        cls.image = os.environ.get('WATCHTOWER_TEST_IMAGE', 'watchtower_web:latest')
        check = subprocess.run(
            ['docker', 'image', 'inspect', cls.image],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        )
        if check.returncode:
            raise RuntimeError('Requested application image is unavailable: ' + cls.image)

    def test_built_image_identity_permissions_and_privileges(self):
        probe = """
import os
from pathlib import Path
import tempfile
assert os.getuid() == os.getgid() == 10001
assert os.environ['HOME'] == '/home/watchtower'
assert os.access('/code/manage.py', os.R_OK)
assert not os.access('/code/manage.py', os.W_OK)
assert not os.access('/code', os.W_OK)
status = Path('/proc/self/status').read_text()
assert 'CapEff:' + chr(9) + '0000000000000000' in status
assert 'NoNewPrivs:' + chr(9) + '1' in status
for directory in ['/run/watchtower', '/var/lib/watchtower', '/code/static', '/code/media', '/code/private-p2p-proofs', '/images', '/home/watchtower']:
    with tempfile.TemporaryFile(dir=directory) as handle:
        handle.write(b'synthetic-probe')
"""
        result = subprocess.run([
            'docker', 'run', '--rm', '--network=none', '--cap-drop=ALL',
            '--security-opt=no-new-privileges:true', '--entrypoint', 'python',
            self.image, '-c', probe,
        ], stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, timeout=60)
        self.assertEqual(result.returncode, 0, result.stdout)
