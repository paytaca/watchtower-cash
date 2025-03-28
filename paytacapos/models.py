from django.db import transaction
from django.db import models
from django.utils import timezone
from django.contrib.postgres.fields import JSONField
from psqlextra.models import PostgresModel
from psqlextra.query import PostgresQuerySet
from main.models import WalletHistory, Wallet, Transaction
from rampp2p.models import PaymentType, PaymentTypeField, FiatCurrency

from decimal import Decimal

from PIL import Image
import os


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

    merchant = models.ForeignKey(
        "Merchant",
        on_delete=models.PROTECT, related_name="devices",
        null=True, blank=True,
    )
    branch = models.ForeignKey(
        "Branch",
        on_delete=models.PROTECT, related_name="devices",
        null=True, blank=True,
    )

    latest_history_record = models.ForeignKey(
        'main.WalletHistory',
        on_delete=models.SET_NULL, related_name="devices",
        null=True, blank=True
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
    
    def populate_latest_history_record(self):
        qs = WalletHistory.objects.filter(record_type='incoming').exclude(amount=0)
        if qs.exists():
            try:
                last_record = qs.filter_pos(self.wallet_hash, self.posid).latest('date_created')
                if last_record:
                    self.latest_history_record = last_record
                    self.save()
            except WalletHistory.DoesNotExist:
                pass

class Location(models.Model):
    landmark = models.TextField(null=True, blank=True, help_text="Other helpful information to locate the place")
    location = models.CharField(max_length=100, null=True, blank=True, help_text="Unit of location that is lower than street")
    street = models.CharField(max_length=60, null=True, blank=True)
    city = models.CharField(max_length=60, null=True, blank=True)
    town = models.CharField(max_length=60, null=True, blank=True)
    province = models.CharField(max_length=60, null=True, blank=True)
    state = models.CharField(max_length=60, null=True, blank=True)
    country = models.CharField(max_length=60, null=True, blank=True)
    longitude = models.DecimalField(max_digits=10, decimal_places=7, null=True, blank=True)
    latitude = models.DecimalField(max_digits=10, decimal_places=7, null=True, blank=True)


class Category(models.Model):
    name = models.CharField(max_length=255, unique=True, primary_key=True)

    class Meta:
        ordering = ('name', )
        verbose_name_plural = 'Categories'


class MerchantQuerySet(PostgresQuerySet):
    def annotate_branch_count(self):
        return self.annotate(
            branch_count=models.Count("branches", distinct=True),
        )

    def annotate_pos_device_count(self):
        return self.annotate(
            pos_device_count=models.Count("devices", distinct=True),
        )

class Merchant(models.Model):
    objects = MerchantQuerySet.as_manager()

    wallet_hash = models.CharField(max_length=75, db_index=True)
    name = models.CharField(max_length=75)
    slug = models.CharField(max_length=255, null=True, blank=True)
    primary_contact_number = models.CharField(max_length=20, null=True, blank=True)
    location = models.OneToOneField(
        Location, on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name="merchant",
    )
    verified = models.BooleanField(default=False)
    gmap_business_link = models.URLField(default=None, blank=True, null=True)
    website_url = models.URLField(max_length=255, null=True, blank=True)
    category = models.ForeignKey(Category, on_delete=models.SET_NULL, null=True, blank=True)
    description = models.TextField(default='', blank=True)
    active = models.BooleanField(default=False)

    logo = models.ImageField(upload_to='merchant_logos', null=True, blank=True)
    logo_30 = models.ImageField(upload_to='merchant_logos', null=True, blank=True)
    logo_60 = models.ImageField(upload_to='merchant_logos', null=True, blank=True)
    logo_90 = models.ImageField(upload_to='merchant_logos', null=True, blank=True)
    logo_120 = models.ImageField(upload_to='merchant_logos', null=True, blank=True)

    last_update = models.DateTimeField(null=True)
    index = models.IntegerField(null=True, blank=True) # index = 2 means that this is the 2nd merchant of a wallet
    pubkey = models.CharField(max_length=100, null=True, blank=True) # 0/{index}

    class Meta:
        ordering = ('-id', )

    def __str__(self):
        return f"Merchant ({self.name})"

    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)

        if self.logo:
            sizes = [
                (30,30),
                (60,60),
                (90,90),
                (120,120),
            ]

            for size in sizes:
                img = Image.open(self.logo.path)
                img.thumbnail(size)
                django_image_name, django_image_ext = os.path.splitext(self.logo.name)
                server_image_name, server_image_ext = os.path.splitext(self.logo.path)

                _size = size[0]

                logo_server_path = f'{server_image_name}_{_size}{server_image_ext}'
                logo_django_path = f'{django_image_name}_{_size}{django_image_ext}'
                img.save(logo_server_path)

                if _size == 30:
                    self.logo_30 = logo_django_path
                elif _size == 60:
                    self.logo_60 = logo_django_path
                elif _size == 90:
                    self.logo_90 = logo_django_path
                elif _size == 120:
                    self.logo_120 = logo_django_path

            super().save(*args, **kwargs)

    @property
    def last_transaction_date(self):
        pos_devices_check = self.devices.filter(latest_history_record__isnull=False)
        pos_latest_tx_date = None
        wallet_latest_tx_date = None

        if pos_devices_check.exists():
            latest_records = []
            for pos in pos_devices_check:
                latest_records.append(pos.latest_history_record.date_created)
            pos_latest_tx_date = max(latest_records)
            #pos_latest_records = WalletHistory.objects.filter(wallet__devices__in=pos_devices_check)
            #pos_latest_tx_date = pos_latest_records.latest('date_created').date_created

        wallet = WalletHistory.objects.filter(wallet__wallet_hash=self.wallet_hash)
        last_tx = wallet.filter(record_type=WalletHistory.INCOMING).latest('date_created')
        if last_tx:
            wallet_latest_tx_date = last_tx.date_created

        merchants_count = Merchant.objects.filter(wallet_hash=self.wallet_hash).count()
        if merchants_count == 1:
            # Return the latest date between pos_latest_tx_date and wallet_latest_tx_date
            return max(filter(None, [pos_latest_tx_date, wallet_latest_tx_date]))
        else:
            # Return the earliest date between pos_latest_tx_date and wallet_latest_tx_date
            return min(filter(None, [pos_latest_tx_date, wallet_latest_tx_date]))

    def get_main_branch(self):
        return self.branches.filter(is_main=True).first()

    @transaction.atomic
    def get_or_create_main_branch(self, force_new=False):
        main_branch = self.get_main_branch()
        if main_branch:
            return main_branch, False

        branch = self.branches.filter(name__icontains="main").first()
        if not branch:
            branch = self.branches.first()

        if branch and not force_new:
            branch.is_main = True
            branch.save()
            return branch, False

        location = None
        if self.location:
            location = self.location
            location.id = None
            location.save()
            self.refresh_from_db()

        branch = Branch.objects.create(
            merchant=self,
            name="Main",
            is_main=True,
            location=location
        )
        return branch, True

    @classmethod
    def get_latest_merchant_index(cls, wallet_hash):
        queryset = cls.objects.filter(
            wallet_hash=wallet_hash,
            active=True,
            verified=True
        ).order_by(
            'index'
        )
        
        index = 0
        for merchant in queryset:
            if merchant.index != index:
                break
            index += 1
        return index

    def sync_main_branch_location(self):
        if not self.location: return

        main_branch = self.branches.filter(is_main=True).first()

        if not main_branch: return

        main_branch_location = main_branch.location or Location()
        new_location = self.location
        new_location.id = main_branch_location.id
        new_location.save()

        if main_branch.location_id != new_location.id:
            main_branch.location = new_location
            main_branch.save()
        return new_location


class Review(models.Model):
    rating = models.PositiveIntegerField()
    comment = models.TextField(blank=True, null=True)
    merchant = models.ForeignKey(Merchant, related_name="reviews", on_delete=models.CASCADE)
    date = models.DateTimeField(default=timezone.now)

    class Meta:
        ordering = ('-date', 'rating', )


class Branch(models.Model):
    merchant = models.ForeignKey(Merchant, on_delete=models.CASCADE, related_name="branches")
    is_main = models.BooleanField(default=False)
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

    def save(self, *args, **kwargs):
        if self.is_main:
            qs = self.__class__.objects.filter(merchant_id = self.merchant_id, is_main=True)
            if self.pk:
              qs = qs.exclude(pk=self.pk)
            has_existing_main = qs.exists()
            if has_existing_main:
                raise Exception("Unable to save as main branch due to existing main branch")

        return super().save(*args, **kwargs)

    def sync_location_to_merchant(self):
        if not self.location: return
        if not self.is_main: return
        if not self.merchant: return

        merchant = self.merchant
        location = merchant.location or Location()
        new_location = self.location
        new_location.id = location.id
        new_location.save()

        if merchant.location_id != new_location.id:
            merchant.location = new_location
            merchant.save()
        return new_location

class PaymentMethod(models.Model):
    payment_type = models.ForeignKey(PaymentType, on_delete=models.CASCADE, related_name="merchant_payment_methods")
    wallet = models.ForeignKey(Wallet, on_delete=models.CASCADE, null=True)
    created_at = models.DateTimeField(auto_now_add=True, editable=False)

    class Meta:
        unique_together = ('payment_type', 'wallet')

    def __str__(self):
        name = self.payment_type.short_name
        if not name:
            name = self.payment_type.full_name
	    
        return str(name)

class PaymentMethodField(models.Model):
    payment_method = models.ForeignKey(PaymentMethod, on_delete=models.CASCADE)
    field_reference = models.ForeignKey(PaymentTypeField, on_delete=models.CASCADE)
    value = models.CharField(max_length=100)
    created_at = models.DateTimeField(auto_now_add=True, editable=False)
    modified_at = models.DateTimeField(auto_now=True)

    def __str__(self):
	    return str(self.id)

class CashOutOrder(PostgresModel):
    class StatusType(models.TextChoices):
        PENDING     = 'PENDING'
        PROCESSING  = 'PROCESSING'
        COMPLETED   = 'COMPLETED'

    currency = models.ForeignKey(
        FiatCurrency,
        on_delete=models.PROTECT,
        related_name="cashout_orders",
        editable=False
    )
    market_price = models.DecimalField(max_digits=18, decimal_places=2, default=0, editable=False)
    wallet = models.ForeignKey(Wallet, on_delete=models.CASCADE, editable=False)
    merchant = models.ForeignKey(Merchant, on_delete=models.CASCADE, null=True)
    status = models.CharField(max_length=50, choices=StatusType.choices, db_index=True, default=StatusType.PENDING) 
    payment_method = models.ForeignKey(PaymentMethod, on_delete=models.SET_NULL, null=True, editable=False)
    payout_details = JSONField(null=True, blank=True, editable=False)
    payout_amount = models.DecimalField(max_digits=18, decimal_places=2, default=0, editable=False)
    sats_amount = models.BigIntegerField(null=True, editable=False)
    created_at = models.DateTimeField(auto_now_add=True, editable=False)
    processed_at = models.DateTimeField(null=True)
    completed_at = models.DateTimeField(null=True)

    def __str__(self):
        return str(self.id)
    
    def save(self, *args, **kwargs):
        if self.pk is not None:
            old_status = CashOutOrder.objects.get(pk=self.pk).status
            if old_status != self.status:
                if self.status == CashOutOrder.StatusType.PENDING:
                    self.processed_at = None
                    self.completed_at = None
                if self.status == CashOutOrder.StatusType.PROCESSING:
                    self.completed_at = None
                    self.processed_at = timezone.now()
                if self.status == CashOutOrder.StatusType.COMPLETED:
                    self.completed_at = timezone.now()
        super(CashOutOrder, self).save(*args, **kwargs)

    def get_input_tx(self):
        inputs = CashOutTransaction.objects.filter(order__id=self.id, record_type=CashOutTransaction.INCOMING)
        return inputs
    
    def get_output_tx(self):
        outputs = CashOutTransaction.objects.filter(order__id=self.id, record_type=CashOutTransaction.OUTGOING)
        return outputs

class CashOutTransaction(models.Model):
    INCOMING = 'incoming'
    OUTGOING = 'outgoing'
    RECORD_TYPE_OPTIONS = [
        (INCOMING, 'Incoming'),
        (OUTGOING, 'Outgoing')
    ]
    record_type = models.CharField(
        max_length=10,
        null=True,
        blank=True,
        db_index=True,
        choices=RECORD_TYPE_OPTIONS
    )
    order = models.ForeignKey(CashOutOrder, on_delete=models.CASCADE)
    txid = models.CharField(max_length=70, db_index=True, null=True)
    transaction = models.OneToOneField(Transaction, on_delete=models.PROTECT, null=True, blank=True)
    wallet_history = models.OneToOneField(WalletHistory, on_delete=models.PROTECT, null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True, editable=False)

    def __str__(self):
        return str(self.id)
    
    @property
    def currency(self):
        return self.order.currency.symbol
    
    @property
    def tx_price(self):
        ''' Fetches the recorded market price when transaction was created. '''
        price = None
        market_prices = self.wallet_history.market_prices
        if market_prices and market_prices.get(self.currency, None):
            price = Decimal(market_prices[self.currency])
        return price
    
    @property
    def order_price(self):
        ''' Fetches the recorded market price when the cash-out order was created. '''
        return Decimal(self.order.market_price)

    @property
    def initial_fiat_value(self):
        ''' Calculates the fiat value of transaction when it was created. '''
        amount = Decimal(self.wallet_history.amount)
        tx_price = self.tx_price
        order_price = self.order_price

        if not tx_price or not order_price:
            return
        
        return round(tx_price * amount, 2)
    
    @property
    def order_fiat_value(self):
        ''' Calculates the fiat value of transaction when the order was created. '''
        amount = Decimal(self.wallet_history.amount)
        tx_price = self.tx_price
        order_price = self.order_price

        if not tx_price or not order_price:
            return

        return round(order_price * amount, 2)
    
class PayoutAddress(models.Model):
    address_index = models.IntegerField(null=True)
    address = models.CharField(max_length=255)
    order = models.OneToOneField(CashOutOrder, on_delete=models.SET_NULL, null=True, related_name="payout_address")
    created_at = models.DateTimeField(auto_now_add=True, editable=False)

    def __str__(self):
        return str(self.address)
