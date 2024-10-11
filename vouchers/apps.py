from django.apps import AppConfig


class VoucherConfig(AppConfig):
    name = 'vouchers'

    def ready(self):
        import vouchers.signals
