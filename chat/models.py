from django.db import models
from psqlextra.models import PostgresModel
from main.models import Address


class PgpInfo(PostgresModel):
    address = models.OneToOneField(
        Address,
        related_name='pgp_info',
        on_delete=models.CASCADE
    )
    user_id = models.CharField(max_length=50)
    email = models.EmailField(max_length=100)
    public_key = models.TextField()
    public_key_hash = models.CharField(max_length=70)
    signature = models.TextField()

    def __str__(self):
        return self.email
