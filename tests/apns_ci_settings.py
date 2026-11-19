"""Minimal settings for the APNs tests, used by `.github/workflows/apns-tests.yml`.

`watchtower.settings` is not imported here on purpose: it initialises
`firebase_admin` from a service-account file and pulls in every app in the
project. The APNs tests only need the push-notifications app plus the real
`build_apns_settings()` output, so this keeps them runnable in CI without
provisioning credentials or a database.
"""
BASE_DIR = "/code"
SECRET_KEY = "apns-tests"
DEBUG = False
ALLOWED_HOSTS = ["*"]

INSTALLED_APPS = [
    "django.contrib.contenttypes",
    "django.contrib.auth",
    "push_notifications",
    "notifications",
]

DATABASES = {
    "default": {"ENGINE": "django.db.backends.sqlite3", "NAME": ":memory:"}
}
USE_TZ = True

from watchtower.apns_settings import build_apns_settings

PUSH_NOTIFICATIONS_SETTINGS = {"CONFIG": "push_notifications.conf.LegacyConfig"}
PUSH_NOTIFICATIONS_SETTINGS.update(build_apns_settings(BASE_DIR))
