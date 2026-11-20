import os

# Settings now require deployment-specific signing keys. Provide deterministic
# test-only values before importing the real settings module; explicit
# environment values (e.g. CI secrets) still take precedence.
os.environ.setdefault(
    'SECRET_KEY',
    'test-only-django-secret-key-0123456789-abcdefghijklmnopqrstuvwxyz',
)
os.environ.setdefault(
    'JWT_SIGNING_KEY',
    'test-only-jwt-signing-key-0123456789-abcdefghijklmnopqrstuvwxyz',
)

from watchtower.settings import *


class DisableMigrations:
    def __contains__(self, item):
        return True
    def __getitem__(self, item):
        return None

MIGRATION_MODULES = DisableMigrations()


