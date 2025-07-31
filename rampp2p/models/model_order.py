from django.db import models
from django.apps import apps
from django.utils import timezone
from datetime import datetime
from django.core.validators import MaxValueValidator, MinValueValidator
from django.utils.translation import gettext_lazy as _
import json

from .model_ad import AdSnapshot, TradeType
from .model_peer import Peer
from .model_arbiter import Arbiter
from .model_payment import PaymentMethod, PaymentType

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
    is_cash_in = models.BooleanField(default=False, db_index=True)

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
        appealable = False
        if self.appealable_at:
            time_now = timezone.make_aware(datetime.now())
            appealable = time_now >= self.appealable_at
        return appealable, self.appealable_at
    
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
    
    def get_seller(self):
        if self.ad_snapshot.trade_type == TradeType.SELL:
            return self.ad_snapshot.ad.owner
        return self.owner
    
    def get_buyer(self):
        if self.ad_snapshot.trade_type == TradeType.BUY:
            return self.ad_snapshot.ad.owner
        return self.owner


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
    def user(self):
        if self.arbiter:
            return self.arbiter
        return self.peer
        
    @property
    def name(self):
        user = self.user
        if user:
            return user.name
    
    @property
    def wallet_hash(self):
        return self.user.wallet_hash

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

class OrderFeedback(models.Model):
    from_peer = models.ForeignKey(Peer, on_delete=models.PROTECT, related_name='created_feedbacks', editable=False)
    to_peer = models.ForeignKey(Peer, on_delete=models.PROTECT, related_name='received_feedbacks', editable=False)
    order = models.ForeignKey(Order, on_delete=models.PROTECT, related_name='feedbacks', editable=False)
    rating = models.IntegerField(validators=[MinValueValidator(1), MaxValueValidator(5)])
    comment = models.CharField(max_length=4000, blank=True)
    created_at = models.DateTimeField(auto_now_add=True, editable=False)
    modified_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return str(self.id)

class ArbiterFeedback(models.Model):
    from_peer = models.ForeignKey(Peer, on_delete=models.PROTECT, related_name='arbiter_feedbacks', editable=False)
    to_arbiter = models.ForeignKey(Arbiter, on_delete=models.PROTECT, related_name='feedbacks', editable=False)
    order = models.ForeignKey(Order, on_delete=models.PROTECT, related_name='arbiter_feedbacks', editable=False)
    rating = models.IntegerField(validators=[MinValueValidator(1), MaxValueValidator(5)])
    comment = models.CharField(max_length=4000, blank=True)
    created_at = models.DateTimeField(auto_now_add=True, editable=False)
    modified_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return str(self.id)

# class kept for legacy purposes
class StatusType(models.TextChoices):
    SUBMITTED         = 'SBM', _('Submitted')
    CONFIRMED         = 'CNF', _('Confirmed')
    ESCROW_PENDING    =  'ESCRW_PN', _('Escrow Pending')
    ESCROWED          = 'ESCRW', _('Escrowed')
    PAID_PENDING      = 'PD_PN', _('Paid Pending')
    PAID              = 'PD', _('Paid')
    APPEALED          = 'APL', _('Appealed')
    RELEASE_PENDING   = 'RLS_PN', _('Release Pending')
    RELEASED          = 'RLS', _('Released')
    REFUND_PENDING    = 'RFN_PN', _('Refund Pending')
    REFUNDED          = 'RFN', _('Refunded')
    CANCELED          = 'CNCL', _('Canceled')

class Status(models.Model):
	class StatusType(models.TextChoices):
		SUBMITTED         = 'SBM', _('Submitted')
		CONFIRMED         = 'CNF', _('Confirmed')
		ESCROW_PENDING    =  'ESCRW_PN', _('Escrow Pending')
		ESCROWED          = 'ESCRW', _('Escrowed')
		PAID_PENDING      = 'PD_PN', _('Paid Pending')
		PAID              = 'PD', _('Paid')
		APPEALED          = 'APL', _('Appealed')
		RELEASE_PENDING   = 'RLS_PN', _('Release Pending')
		RELEASED          = 'RLS', _('Released')
		REFUND_PENDING    = 'RFN_PN', _('Refund Pending')
		REFUNDED          = 'RFN', _('Refunded')
		CANCELED          = 'CNCL', _('Canceled')

	status = models.CharField(max_length=10, choices=StatusType.choices, blank=False, db_index=True)
	order = models.ForeignKey(Order, on_delete=models.CASCADE)
	created_at = models.DateTimeField(auto_now_add=True, editable=False, db_index=True)
	created_by = models.CharField(max_length=75, db_index=True, null=True, blank=True)
	seller_read_at = models.DateTimeField(null=True, blank=True)
	buyer_read_at = models.DateTimeField(null=True, blank=True)

	def __str__(self):
		return str(self.id)
	
	def get_creator(self):
		creator = None
		wallet_hash = self.created_by

		if wallet_hash:
			Arbiter = apps.get_model('rampp2p', 'Arbiter')
			arbiter = Arbiter.objects.filter(wallet_hash=wallet_hash)
			if arbiter.exists():
				creator = arbiter.first()
			else:
				Peer = apps.get_model('rampp2p', 'Peer')
				peer = Peer.objects.filter(wallet_hash=wallet_hash)
				if peer.exists():
					creator = peer.first()
		
		return creator

class AppealType(models.TextChoices):
    RELEASE = 'RLS', _('Release')
    REFUND  = 'RFN', _('Refund')

class Appeal(models.Model):
    type = models.CharField(max_length=10, choices=AppealType.choices, db_index=True)
    reasons = models.TextField(blank=True, null=True)
    owner = models.ForeignKey(Peer, on_delete=models.PROTECT, related_name='created_appeals')
    order = models.OneToOneField(Order, on_delete=models.CASCADE, related_name='appeal')
    resolved_at = models.DateTimeField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return str(self.id)

    def set_reasons(self, reasons):
        self.reasons = json.dumps(reasons)
    
    def get_reasons(self):
        return json.loads(self.reasons) if self.reasons else []

class Contract(models.Model):
    order = models.OneToOneField(Order, on_delete=models.CASCADE, unique=True)
    address = models.CharField(max_length=100, blank=True, null=True)
    version = models.CharField(max_length=100, null=True)
    service_fee = models.IntegerField(null=True, editable=False)
    arbitration_fee = models.IntegerField(null=True, editable=False)
    contract_fee = models.IntegerField(null=True, editable=False)
    created_at = models.DateTimeField(auto_now_add=True, editable=False)

    def __str__(self):
        return f'{self.id}'
    
    def get_total_fees(self):
        total = None
        try:
            total = self.service_fee + self.arbitration_fee + self.contract_fee
        except Exception as err:
            logger.exception(err.args[0])
        return total
    
    def get_fees(self):
        return {
            'service_fee': self.service_fee,
            'arbitration_fee': self.arbitration_fee,
            'contract_fee': self.contract_fee
        }
    
    def get_members(self):
        members = ContractMember.objects.filter(contract__id=self.id)
        arbiter, seller, buyer = None, None, None
        for member in members:
            type = member.member_type
            if (type == ContractMember.MemberType.ARBITER):
                arbiter = member
            if (type == ContractMember.MemberType.SELLER):
                seller = member
            if (type == ContractMember.MemberType.BUYER):
                buyer = member
        
        return {
            'arbiter': arbiter, 
            'seller': seller, 
            'buyer': buyer
        }

class ContractMember(models.Model):
    class MemberType(models.TextChoices):
        SELLER = 'SELLER'
        BUYER = 'BUYER'
        ARBITER = 'ARBITER'

    contract = models.ForeignKey(Contract, on_delete=models.CASCADE, related_name='members')
    member_ref_id = models.IntegerField()
    member_type = models.CharField(max_length=10, choices=MemberType.choices)
    pubkey = models.CharField(max_length=75)
    address = models.CharField(max_length=75)
    address_path = models.CharField(max_length=10, null=True)
    created_at = models.DateTimeField(auto_now_add=True, editable=False)

    class Meta:
        unique_together = ('contract', 'member_type')

    def __str__(self):
        return f'{self.address}'

class Transaction(models.Model):
    class ActionType(models.TextChoices):
        ESCROW = 'ESCROW'
        REFUND = 'REFUND'
        RELEASE = 'RELEASE'

    contract = models.ForeignKey(Contract, on_delete=models.CASCADE, editable=False)
    action = models.CharField(max_length=50, choices=ActionType.choices, db_index=True)
    txid = models.CharField(max_length=200, unique=True, null=True, db_index=True)
    valid = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True, editable=False)

    def __str__(self):
        return f'{self.id}'

class Recipient(models.Model):
    transaction = models.ForeignKey(Transaction, on_delete=models.CASCADE, related_name="recipients", editable=False)
    address = models.CharField(max_length=200)
    value = models.DecimalField(max_digits=18, decimal_places=8, default=0, editable=False)
    created_at = models.DateTimeField(auto_now_add=True, editable=False)

    def __str__(self):
        return f'{self.id}'