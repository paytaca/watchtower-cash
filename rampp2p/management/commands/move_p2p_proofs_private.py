import hashlib
import os
import shutil
from pathlib import Path
from tempfile import NamedTemporaryFile

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

from rampp2p.proof_storage import bounded_path, contained, legacy_proof_root, private_proof_root


def digest(path):
    hasher = hashlib.sha256()
    with path.open('rb') as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b''):
            hasher.update(chunk)
    return hasher.digest()


class Command(BaseCommand):
    help = 'Move legacy P2P proof files outside public media; dry-run unless --apply is supplied.'

    def add_arguments(self, parser):
        parser.add_argument('--apply', action='store_true')

    def handle(self, *args, **options):
        source_root, target_root = legacy_proof_root(), private_proof_root()
        media_root = Path(settings.MEDIA_ROOT).resolve()
        if (source_root == media_root or not contained(source_root, media_root)
                or contained(source_root, target_root) or contained(target_root, source_root)):
            raise CommandError('Legacy and private proof roots must be separate; legacy proofs must be beneath MEDIA_ROOT.')
        plan = []
        # Preflight the whole tree before moving any file. Never follow source
        # symlinks or overwrite a different destination file.
        for source in sorted(source_root.rglob('*')) if source_root.exists() else []:
            if source.is_symlink():
                raise CommandError('Legacy proof storage contains a symlink; resolve it before moving files.')
            if not source.is_file():
                continue
            try:
                target = bounded_path(target_root, source.relative_to(source_root))
            except (OSError, ValueError, RuntimeError) as err:
                raise CommandError('Invalid destination proof path.') from err
            if target.exists() and (not target.is_file() or digest(source) != digest(target)):
                raise CommandError('A destination proof file already exists with different contents.')
            plan.append((source, target))
        if not options['apply']:
            self.stdout.write(f'DRY RUN: {len(plan)} legacy proof files eligible; no files changed. Use --apply to move them.')
            return
        for source, target in plan:
            target.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
            temporary_path = None
            try:
                with NamedTemporaryFile(dir=target.parent, delete=False) as temporary:
                    temporary_path = Path(temporary.name)
                    with source.open('rb') as stream:
                        shutil.copyfileobj(stream, temporary)
                    temporary.flush()
                    os.fsync(temporary.fileno())
                if digest(source) != digest(temporary_path):
                    raise CommandError('A source file changed during the move; retry after stopping legacy upload writers.')
                try:
                    # Atomic, exclusive creation on the destination filesystem.
                    os.link(temporary_path, target)
                except FileExistsError:
                    if digest(temporary_path) != digest(target):
                        raise CommandError('A destination proof file appeared with different contents.')
                source.unlink()
            finally:
                if temporary_path is not None:
                    temporary_path.unlink(missing_ok=True)
        self.stdout.write(f'Moved {len(plan)} proof files to private storage; legacy public copies removed.')
