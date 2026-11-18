from django.apps import AppConfig


class NotificationsConfig(AppConfig):
    name = 'notifications'

    def ready(self):
        # apns2 0.7.x is incompatible with PyJWT 2.x; patch its credentials
        # before any APNs send. See notifications/utils/apns_compat.py.
        from notifications.utils import apns_compat

        apns_compat.install()
