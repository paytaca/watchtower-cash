from django.dispatch import receiver
from django.db.backends.signals import connection_created
from main.tasks import slpfountainhead, slpbitcoin

@receiver(connection_created)
def startup_commands(connection, **kwargs):
    with connection.cursor() as cursor:
        slpfountainhead.delay()
        slpbitcoin.delay()