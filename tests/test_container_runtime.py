"""Static and optional runtime checks for the hardened container.

The static checks are safe in any environment. The Docker checks are opt-in:

    RUN_CONTAINER_RUNTIME_TESTS=1 python -m unittest tests.test_container_runtime -v

Set ``WATCHTOWER_TEST_IMAGE`` to test a locally built image. Without Docker or
without the image, the runtime checks are skipped rather than failed.
"""
import os
from pathlib import Path
import re
import shutil
import subprocess
import unittest

ROOT = Path(__file__).resolve().parents[1]


class ContainerConfigurationTests(unittest.TestCase):
    def test_image_runs_as_unprivileged_uid_and_gid(self):
        dockerfile = (ROOT / 'Dockerfile').read_text()
        self.assertIn('groupadd --gid 10001 app', dockerfile)
        self.assertIn('useradd --uid 10001 --gid 10001', dockerfile)
        self.assertRegex(dockerfile, r'(?m)^USER 10001:10001$')
        self.assertNotRegex(dockerfile, r'(?m)^USER root$')
        self.assertIn('PYTHONDONTWRITEBYTECODE=1', dockerfile)

    def test_only_runtime_data_directories_are_writable(self):
        dockerfile = (ROOT / 'Dockerfile').read_text()
        chown = re.search(r'chown -R app:app ([^\n]+)', dockerfile)
        self.assertIsNotNone(chown)
        owned = chown.group(1).split()
        for path in ('/code/static', '/code/media', '/code/private-p2p-proofs'):
            self.assertIn(path, owned)
        self.assertIn('/var/run/watchtower', owned)
        self.assertNotIn('/code', owned)
        self.assertNotIn('/code/main', owned)

    def test_supervisor_and_beat_use_writable_runtime_paths(self):
        for name in ('supervisord.conf', 'supervisord-mainnet.conf'):
            with self.subTest(config=name):
                text = (ROOT / name).read_text()
                self.assertNotIn('/var/run/supervisor.sock', text)
                self.assertIn('/var/run/watchtower/supervisor.sock', text)
                self.assertIn('pidfile=/var/run/watchtower/supervisord.pid', text)
                self.assertIn('logfile=/var/run/watchtower/supervisord.log', text)
                self.assertIn('childlogdir=/var/run/watchtower', text)
                self.assertIn(
                    'celery -A watchtower beat '
                    '--schedule=/var/run/watchtower/celerybeat-schedule',
                    text,
                )

    def test_production_compose_drops_privileges(self):
        for name in ('compose/mainnet.yml', 'compose/chipnet.yml'):
            with self.subTest(compose=name):
                text = (ROOT / name).read_text()
                self.assertIn('user: "10001:10001"', text)
                self.assertIn('no-new-privileges:true', text)
                self.assertIn('cap_drop:', text)
                self.assertIn('- ALL', text)
                self.assertIn(
                    'APNS_AUTH_KEY_PATH: /run/watchtower-credentials/APNS_AuthKey.p8',
                    text,
                )

    def test_security_audit_notes_are_not_part_of_the_image_context(self):
        self.assertIn('SECURITY_AUDIT', (ROOT / '.dockerignore').read_text())


@unittest.skipUnless(
    os.environ.get('RUN_CONTAINER_RUNTIME_TESTS') == '1',
    'set RUN_CONTAINER_RUNTIME_TESTS=1 to run container checks',
)
class ContainerRuntimeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if not shutil.which('docker'):
            raise unittest.SkipTest('Docker CLI is unavailable')
        cls.image = os.environ.get('WATCHTOWER_TEST_IMAGE', 'watchtower_web:latest')
        result = subprocess.run(
            ['docker', 'image', 'inspect', cls.image],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        )
        if result.returncode != 0:
            raise unittest.SkipTest('container image is unavailable: ' + cls.image)

    def run_container(self, *command, entrypoint=None):
        args = ['docker', 'run', '--rm', '--network=none']
        if entrypoint:
            args.extend(['--entrypoint', entrypoint])
        args.extend([self.image, *command])
        return subprocess.run(
            args, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
            text=True, timeout=60, check=True,
        )

    def test_runtime_process_is_not_root(self):
        result = self.run_container(entrypoint='id')
        self.assertIn('uid=10001', result.stdout)
        self.assertIn('gid=10001', result.stdout)

    def test_source_is_read_only_but_runtime_directories_are_writable(self):
        command = (
            'test -r /code/manage.py && '
            'test ! -w /code/manage.py && '
            'test -w /code/static && '
            'test -w /code/media && '
            'test -w /var/run/watchtower'
        )
        self.run_container('-c', command, entrypoint='sh')

    def test_supervisor_can_write_its_socket_directory(self):
        command = (
            'python - <<"PY"\n'
            'from pathlib import Path\n'
            'root = Path("/var/run/watchtower")\n'
            'probe = root / "write-probe"\n'
            'probe.write_text("ok")\n'
            'probe.unlink()\n'
            'assert root.is_dir()\n'
            'PY'
        )
        self.run_container('-c', command, entrypoint='sh')
