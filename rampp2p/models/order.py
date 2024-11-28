from django.db import models
from django.apps import apps
from django.utils import timezone
from datetime import datetime

from .ad import AdSnapshot, TradeType
from .peer import Peer
from .arbiter import Arbiter
from .payment import PaymentMethod, PaymentType

class Order(models.Model):
    tracking_id = models.CharField(max_length=50, null=True, blank=True, unique=True)
    ad_snapshot = models.ForeignKey(AdSnapshot, on_delete=models.PROTECT, editable=False)
    owner = models.ForeignKey(Peer, on_delete=models.PROTECT, editable=False, related_name="created_orders")
    chat_session_ref = models.CharField(max_length=100, null=True, blank=True)
    arbiter = models.ForeignKey(Arbiter, on_delete=models.PROTECT, blank=True, null=True, related_name="arbitrated_orders")
    locked_price = models.DecimalField(max_digits=18, decimal_places=8, default=0, editable=False)
    crypto_amount = models.DecimalField(max_digits=18, decimal_places=8, default=0, null=True, editable=False) # order trade amount in BCH (to be deprecated)
    trade_amount = models.BigIntegerField(null=True) # order trade amount in satoshis
    payment_methods = models.ManyToManyField(PaymentMethod)
    created_at = models.DateTimeField(auto_now_add=True, editable=False)
    appealable_at = models.DateTimeField(null=True)
    expires_at = models.DateTimeField(null=True)
    is_cash_in = models.BooleanField(default=False)

    def __str__(self):
        return f'{self.id}'
    
    @property
    def status(self):
        Status = apps.get_model('rampp2p', 'Status')
        last_status = Status.objects.filter(order__id=self.id).last()
        return last_status
    
    @property
    def trade_type(self):
        if self.ad_snapshot.trade_type == TradeType.SELL:
            return TradeType.BUY
        return TradeType.SELL
    
    @property
    def currency(self):
        return self.ad_snapshot.fiat_currency
    
    def is_appealable(self):
        time_now = timezone.make_aware(datetime.now())
        return time_now >= self.appealable_at, self.appealable_at
    
    def get_members(self):
        OrderMember = apps.get_model('rampp2p', 'OrderMember')
        members = OrderMember.objects.filter(order__id=self.id)
        arbiter, seller, buyer = None, None, None
        for member in members:
            type = member.type
            if (type == OrderMember.MemberType.ARBITER):
                arbiter = member
            if (type == OrderMember.MemberType.SELLER):
                seller = member
            if (type == OrderMember.MemberType.BUYER):
                buyer = member

        return {
            'arbiter': arbiter,
            'seller': seller,
            'buyer': buyer
        }
    
    def is_seller(self, wallet_hash):
        seller = self.owner
        if self.ad_snapshot.trade_type == 'SELL':
            seller = self.ad_snapshot.ad.owner
        if wallet_hash == seller.wallet_hash:
            return True
        return False

    def is_buyer(self, wallet_hash):
        buyer = self.owner
        if self.ad_snapshot.trade_type == 'BUY':
            buyer = self.ad_snapshot.ad.owner
        if wallet_hash == buyer.wallet_hash:
            return True
        return False
    
    def is_arbiter(self, wallet_hash):
        return wallet_hash == self.arbiter.wallet_hash


class OrderPayment(models.Model):
    order = models.ForeignKey(Order, on_delete=models.CASCADE)
    payment_method = models.ForeignKey(PaymentMethod, on_delete=models.SET_NULL, null=True)
    payment_type = models.ForeignKey(PaymentType, on_delete=models.PROTECT)

class ImageUpload(models.Model):
    url = models.URLField(null=True, blank=True)
    url_path = models.CharField(max_length=256, null=True, blank=True)
    file_hash = models.CharField(max_length=70, null=True, blank=True, unique=True)
    size = models.IntegerField(null=True, blank=True)

class OrderPaymentAttachment(models.Model):
    payment = models.ForeignKey(OrderPayment, on_delete=models.CASCADE)
    image = models.ForeignKey(ImageUpload, on_delete=models.CASCADE)
    created_at = models.DateTimeField(auto_now_add=True)
        
class OrderMember(models.Model):
    class MemberType(models.TextChoices):
        SELLER = 'SELLER'
        BUYER = 'BUYER'
        ARBITER = 'ARBITER'

    type = models.CharField(max_length=10, choices=MemberType.choices, null=True)
    order = models.ForeignKey(Order, on_delete=models.CASCADE, related_name='members')
    peer = models.ForeignKey(Peer, on_delete=models.CASCADE, related_name='order_members', null=True, blank=True)
    arbiter = models.ForeignKey(Arbiter, on_delete=models.CASCADE, related_name='order_members', null=True, blank=True)
    read_at = models.DateTimeField(null=True, blank=True)

    def __str__(self) -> str:
        return f'{self.id}'

    @property
    def name(self):
        if self.peer:
           return self.peer.name
        elif self.arbiter:
            return self.arbiter.name
    
    @property
    def wallet_hash(self):
        if self.peer:
            return self.peer.wallet_hash
        elif self.arbiter:
            return self.arbiter.wallet_hash

    class Meta:
         constraints = [
            models.UniqueConstraint(
                fields=['type', 'peer', 'order'],
                condition=models.Q(peer__isnull=False),
                name='unique_peer_order'
            ),
            models.UniqueConstraint(
                fields=['type', 'arbiter', 'order'],
                condition=models.Q(arbiter__isnull=False),
                name='unique_arbiter_order'
            ),
        ]

