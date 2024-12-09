from django.db import models
from django.utils.translation import gettext_lazy as _
from django.apps import apps
from .order import Order

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