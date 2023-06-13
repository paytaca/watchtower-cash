from django.db import models
from main.models import WalletHistory


class LinkedDeviceInfo(models.Model):
    link_code = models.CharField(max_length=100, unique=True)

    device_id = models.CharField(max_length=50, null=True, blank=True)
    name = models.CharField(max_length=50, null=True, blank=True)
    device_model = models.CharField(max_length=50, null=True, blank=True)
    os = models.CharField(max_length=15, null=True, blank=True)
    is_suspended = models.BooleanField(default=False)

    def get_unlink_request(self):
        try:
            return self.unlink_request
        except LinkedDeviceInfo.unlink_request.RelatedObjectDoesNotExist:
            pass


class UnlinkDeviceRequest(models.Model):
    linked_device_info = models.OneToOneField(
        LinkedDeviceInfo,
        on_delete=models.CASCADE,
        related_name="unlink_request",
    )

    force = models.BooleanField(default=False)
    signature = models.TextField(
        help_text="Signed data of link_code"
    )
    nonce = models.IntegerField()
    updated_at = models.DateTimeField(auto_now=True)

    @property
    def message(self):
        return self.linked_device_info.link_code


class PosDevice(models.Model):
    posid = models.IntegerField()
    wallet_hash = models.CharField(max_length=70)

    name = models.CharField(max_length=100, null=True, blank=True)
    linked_device = models.OneToOneField(
        LinkedDeviceInfo,
        on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name="pos_device",
    )

    branch = models.ForeignKey(
        "Branch",
        on_delete=models.SET_NULL, related_name="devices",
        null=True, blank=True,
    )

    class Meta:
        unique_together = (
            ("posid", "wallet_hash"),
        )

    @classmethod
    def find_new_posid(cls, wallet_hash):
        queryset = cls.objects.filter(wallet_hash=wallet_hash)
        last_posid = queryset.aggregate(max=models.Max("posid"))["max"]
        if last_posid is not None and last_posid+1 < 10 ** 4:
            return last_posid + 1

        posids = queryset.values_list("posid", flat=True).distinct()
        for i in range(10**4):
            if i not in posids:
                return i

        return None


class Location(models.Model):
    landmark = models.TextField(null=True, blank=True, help_text="Other helpful information to locate the place")
    location = models.CharField(max_length=100, null=True, blank=True, help_text="Unit of location that is lower than street")
    street = models.CharField(max_length=60, null=True, blank=True)
    city = models.CharField(max_length=60, null=True, blank=True)
    country = models.CharField(max_length=60, null=True, blank=True)
    longitude = models.DecimalField(max_digits=10, decimal_places=7, null=True, blank=True)
    latitude = models.DecimalField(max_digits=10, decimal_places=7, null=True, blank=True)


class Merchant(models.Model):
    wallet_hash = models.CharField(max_length=75, unique=True, db_index=True)
    name = models.CharField(max_length=75)
    primary_contact_number = models.CharField(max_length=20, null=True, blank=True)
    location = models.OneToOneField(
        Location, on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name="merchant",
    )
    verified = models.BooleanField(default=False)
    gmap_business_link = models.URLField(default=None, blank=True, null=True)
    active = models.BooleanField(default=False)


    def __str__(self):
        return f"Merchant ({self.name})"

    @property
    def last_transaction_date(self):
        wallet = WalletHistory.objects.filter(wallet__wallet_hash=self.wallet_hash)
        last_tx = wallet.filter(record_type=WalletHistory.INCOMING).latest('date_created')
        last_tx_date = None
        if last_tx:
            last_tx_date = str(last_tx.date_created)
        return last_tx_date


class Branch(models.Model):
    merchant = models.ForeignKey(Merchant, on_delete=models.CASCADE, related_name="branches")
    name = models.CharField(max_length=75)
    location = models.OneToOneField(
        Location, on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name="branch",
    )

    class Meta:
        verbose_name_plural = "branches"

    def __str__(self):
        return f"Branch ({self.merchant.name} - {self.name})"
