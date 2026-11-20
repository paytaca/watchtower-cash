"""Opt-in integration check using Docker's actual ignore matcher and COPY.

Run with RUN_DOCKER_CONTEXT_TESTS=1 python -m unittest tests.test_docker_build_context.
Only synthetic files are sent to Docker; repository credentials are never read.
"""
import os
from pathlib import Path
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]


@unittest.skipUnless(os.environ.get('RUN_DOCKER_CONTEXT_TESTS') == '1', 'requires local Docker')
class DockerBuildContextTests(unittest.TestCase):
    def test_copy_excludes_private_files_and_preserves_application_sources(self):
        blocked = [
            '.env', '.env_dev', '.env.prod', '.env_template', 'compose/.env_mainnet',
            'nested/.env_testnet', '.git/config', 'nested/.git/objects/example',
            '.ssh/id_rsa', '.aws/credentials', '.config/gcloud/token',
            'compose/firebase-admin-credentials.json', 'nested/service-account.json',
            'nested/service_account.json', 'compose/APNS_AuthKey.p8',
            'main/utils/queries/ssl/server.key', 'nested/private.pem',
            'nested/private.p12', 'nested/private.pfx',
            'private-security/evidence.bin', 'private-p2p-proofs/proof.png',
            'nested/private-security/evidence.bin', 'media/proof.png', 'images/image.png',
            'nested/debug.log', 'db.sqlite3', 'db.sqlite3-wal', 'backup.dump',
            'dump.rdb', '.venv/lib/example.py', 'venv/bin/python', 'myenv/bin/python',
            'nested/__pycache__/example.pyc', 'nested/node_modules/package/index.js',
        ]
        allowed = [
            'requirements.txt', 'manage.py', 'entrypoint.sh', 'watchtower/settings.py',
            'supervisord-mainnet.conf', 'compose/mainnet.yml', 'compose/nginx.conf',
            'main/templates/main/assetlinks.json', 'main/static/style.css',
            'main/utils/queries/ssl/server.crt',
        ]
        for app in ['main', 'anyhedge', 'rampp2p', 'cts', 'stablehedge', 'multisig']:
            allowed.extend([app + '/js/package.json', app + '/js/package-lock.json', app + '/js/server.js'])
        with tempfile.TemporaryDirectory(prefix='watchtower-context-check-') as directory:
            context = Path(directory) / 'context'
            context.mkdir()
            output = Path(directory) / 'output'
            (context / '.dockerignore').write_text((ROOT / '.dockerignore').read_text())
            (context / 'Dockerfile').write_text('FROM scratch\nCOPY . /context/\n')
            for name in blocked + allowed:
                path = context / name
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text('synthetic-test-data\n')
            result = subprocess.run([
                'docker', 'build', '--network=none', '--progress=plain',
                '--output', 'type=local,dest=' + str(output), str(context),
            ], stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, timeout=120)
            self.assertEqual(result.returncode, 0, result.stdout)
            for name in blocked:
                self.assertFalse((output / 'context' / name).exists(), 'Private file copied: ' + name)
            for name in allowed:
                self.assertTrue((output / 'context' / name).is_file(), 'Required source excluded: ' + name)
