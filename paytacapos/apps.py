from django.db.models.signals import post_migrate
from django.apps import AppConfig


def generate_vault_for_existing_devices(*args, **kwargs):
    from vouchers.vault import generate_voucher_vault
    from paytacapos.models import PosDevice

    for pos_device in PosDevice.objects.all():
        generate_voucher_vault(pos_device.id)


class PaytacaposConfig(AppConfig):
    # default_auto_field = 'django.db.models.BigAutoField'
    name = 'paytacapos'

    def ready(self):
        import paytacapos.signals

        post_migrate.connect(generate_vault_for_existing_devices, sender=self)
