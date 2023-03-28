from django.utils import timezone
from django.db import models
from django.contrib.postgres.fields import JSONField
from django.utils.translation import gettext_lazy as _
from django.core.validators import MaxValueValidator, MinValueValidator

# Create your models here.
class Shift(models.Model):
    wallet_hash = models.CharField(max_length=100)
    bch_address = models.CharField(max_length=100)
    ramp_type =  models.CharField(max_length=20)
    shift_id = models.CharField(max_length=50, unique=True)
    quote_id = models.CharField(max_length=50, unique=True)
    date_shift_created = models.DateTimeField(null=True, blank=True)
    date_shift_completed = models.DateTimeField(null=True, blank=True)
    shift_info = JSONField(default=dict)
    shift_status = models.CharField(max_length=50, default="waiting")

#### Ramp P2P models

class Peer(models.Model):
    nickname = models.CharField(max_length=100, unique=True)
    default_fiat = models.ForeignKey('FiatCurrency', on_delete=models.SET_NULL, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    modified_at = models.DateTimeField(auto_now=True)

class FiatCurrency(models.Model):
    name = models.CharField(max_length=100)
    abbrev = models.CharField(max_length=3)
    created_at = models.DateTimeField(auto_now_add=True)

class CryptoCurrency(models.Model):
    name = models.CharField(max_length=100)
    abbrev = models.CharField(max_length=10)
    created_at = models.DateTimeField(auto_now_add=True)

class PaymentType(models.Model):
    name = models.CharField(max_length=100)
    is_disabled = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    modified_at = models.DateTimeField(auto_now=True)

class PaymentMethod(models.Model):
    payment_type = models.ForeignKey('PaymentType', on_delete=models.PROTECT)
    owner = models.ForeignKey('Peer', on_delete=models.CASCADE)
    account_name = models.CharField(max_length=100)
    account_number = models.CharField(max_length=100)
    created_at = models.DateTimeField(auto_now_add=True)
    modified_at = models.DateTimeField(auto_now=True)

class Ad(models.Model):

    class TradeType(models.TextChoices):
        SELL = 'SELL'
        BUY = 'BUY'
    
    class PriceType(models.TextChoices):
        FIXED = 'FIXED'
        FLOATING = 'FLOATING'

    owner = models.ForeignKey('Peer', on_delete=models.PROTECT)
    trade_type = models.CharField(max_length=4, choices=TradeType.choices)
    price_type = models.CharField(max_length=10, choices=PriceType.choices)
    fiat_currency = models.ForeignKey('FiatCurrency', on_delete=models.PROTECT)
    crypto_currency = models.ForeignKey('CryptoCurrency', on_delete=models.PROTECT)
    fixed_price = models.FloatField()
    floating_price = models.FloatField()
    trade_floor = models.FloatField()
    trade_ceiling = models.FloatField()
    crypto_amount = models.FloatField()
    time_limit = models.IntegerField()
    payment_methods = models.ManyToManyField('PaymentMethod')
    created_at = models.DateTimeField(auto_now_add=True)
    modified_at = models.DateTimeField(auto_now=True)
    is_deleted = models.BooleanField(default=False)
    deleted_at = models.DateTimeField(blank=True, null=True)

    # modified for soft deletion
    def delete(self, *args, **kwargs):
        self.is_deleted = True
        self.deleted_at = timezone.now()
        self.save()

    class Meta:
        # Exclude deleted records by default
        # Use `MyModel.all_objects` to retrieve all records
        default_manager_name = 'objects'
        ordering = ['-id']

    objects = models.Manager()
    all_objects = models.Manager.with_deleted()

class Order(models.Order):
    ad = models.ForeignKey('Ad', on_delete=models.PROTECT, editable=False)
    creator = models.ForeignKey('Peer', on_delete=models.PROTECT, editable=False)
    fiat_amount = models.FloatField(editable=False)
    locked_price = models.FloatField(editable=False)
    arbiter = models.ForeignKey('Arbiter', on_delete=models.PROTECT, editable=False)
    contract_address = models.CharField(max_length=50, blank=True, null=True, editable=False)
    chat_room = models.ForeignKey('ChatRoom', on_delete=models.PROTECT, editable=False)
    is_appealed = models.BooleanField(default=False)
    buyer_feedback = models.ForeignKey('PeerFeedback', on_delete=models.PROTECT, blank=True, null=True)
    seller_feedback = models.ForeignKey('PeerFeedback', on_delete=models.PROTECT, blank=True, null=True)
    arbiter_feedback = models.ForeignKey('ArbiterFeedback', on_delete=models.PROTECT, blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True, editable=False)

    # TODO: should not be deletable

class Status(models.Model):

    class StatusType(models.TextChoices):
        SUBMITTED = 'SBM', _('Submitted')
        CONFIRMED = 'CNF', _('Confirmed')
        PAID      = 'PD', _('Paid')
        APPEALED  = 'APL', _('Appealed')
        RELEASED  = 'RLS', _('Released')
        REFUNDED  = 'RFN', _('Refunded')

    status = models.CharField(max_length=3, choices=StatusType.choices, editable=False)
    order = models.ForeignKey('Order', on_delete=models.CASCADE, editable=False)
    created_at = models.DateTimeField(auto_now_add=True, editable=False)

    # TODO: should not be deletable

class ChatRoom(models.Model):
    members = models.ManyToManyField('Peer')
    created_at = models.DateTimeField(auto_now_add=True, editable=False)

    # TODO: should not be deletable

class Message(models.Model):
    from_peer = models.ForeignKey('Peer', on_delete=models.PROTECT, editable=False)
    chat_room = models.ForeignKey('ChatRoom', on_delete=models.PROTECT, editable=False)
    message = models.CharField(max_length=4000, editable=False)
    created_at = models.DateTimeField(auto_now_add=True, editable=False)

class Arbiter(models.Model):
    name = models.CharField(max_length=100)
    wallet_address = models.CharField(max_length=50)
    is_disabled = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True, editable=False)
    modified_at = models.DateTimeField(auto_now=True)

class ArbiterFeedback(models.Model):
    from_peer = models.ForeignKey('Peer', on_delete=models.PROTECT, editable=False)
    to_arbiter = models.ForeignKey('Arbiter', on_delete=models.PROTECT, editable=False)
    order = models.ForeignKey('Order', on_delete=models.PROTECT, editable=False)
    rating = models.IntegerField(validators=[MinValueValidator(1), MaxValueValidator(5)])
    comment = models.CharField(max_length=4000, blank=True)
    created_at = models.DateTimeField(auto_now_add=True, editable=False)
    modified_at = models.DateTimeField(auto_now=True)

class PeerFeedback(models.Model):
    from_peer = models.ForeignKey('Peer', editable=False)
    to_peer = models.ForeignKey('Peer', editable=False)
    rating = models.IntegerField(validators=[MinValueValidator(1), MaxValueValidator(5)])
    comment = models.CharField(max_length=4000, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    modified_at = models.DateTimeField(auto_now=True)

