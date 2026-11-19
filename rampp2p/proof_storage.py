"""Private payment-proof storage and bounded legacy-path resolution."""
from pathlib import Path
from urllib.parse import unquote, urlsplit

from django.conf import settings
from django.core.exceptions import ImproperlyConfigured


def contained(path, root):
    try:
        path.relative_to(root)
        return True
    except ValueError:
        return False


def private_proof_root():
    configured = getattr(settings, 'P2P_PROOF_ROOT', None)
    root = Path(configured or Path(settings.MEDIA_ROOT).parent / 'private-p2p-proofs').resolve()
    public_roots = [Path(settings.MEDIA_ROOT).resolve()]
    if getattr(settings, 'STATIC_ROOT', None):
        public_roots.append(Path(settings.STATIC_ROOT).resolve())
    if any(contained(root, public) or contained(public, root) for public in public_roots):
        raise ImproperlyConfigured('P2P_PROOF_ROOT must not overlap public media or static roots.')
    return root


def legacy_proof_root():
    return Path(settings.IMAGE_UPLOAD_ROOT).resolve()


def proof_relative_path(url_path):
    if not isinstance(url_path, str):
        raise ValueError('Invalid proof path')
    path = unquote(urlsplit(url_path).path)
    prefix = unquote(urlsplit(settings.IMAGE_UPLOAD_PATH).path).rstrip('/') + '/'
    if not path.startswith(prefix):
        raise ValueError('Invalid proof path')
    relative = Path(path[len(prefix):])
    if relative.is_absolute() or not relative.parts or '..' in relative.parts or '\x00' in path:
        raise ValueError('Invalid proof path')
    return relative


def bounded_path(root, relative, strict=False):
    if relative.is_absolute() or '..' in relative.parts:
        raise ValueError('Invalid proof path')
    result = (root / relative).resolve(strict=strict)
    if not contained(result, root):
        raise ValueError('Invalid proof path')
    return result


def proof_file_path(url_path):
    relative = proof_relative_path(url_path)
    for root in (private_proof_root(), legacy_proof_root()):
        try:
            candidate = bounded_path(root, relative, strict=True)
            if candidate.is_file():
                return candidate
        except FileNotFoundError:
            continue
    raise FileNotFoundError('Proof file unavailable')


def is_public_proof_path(relative, resolved_file):
    # Block even orphaned legacy uploads and aliases into either storage root.
    folder = Path(getattr(settings, 'IMAGE_UPLOAD_FOLDER', 'image_uploads'))
    if contained(relative, folder):
        return True
    roots = [legacy_proof_root(), private_proof_root()]
    return any(contained(resolved_file, root) for root in roots)
