from django.db import models
from django.apps import apps
from django.utils.crypto import get_random_string

class Peer(models.Model):
    chat_identity_id = models.IntegerField(null=True, blank=True)
    name = models.CharField(max_length=64, unique=True)
    wallet_hash = models.CharField(max_length=75, unique=True, db_index=True)
    public_key = models.CharField(max_length=75)
    address = models.CharField(max_length=75)
    address_path = models.CharField(max_length=10, null=True)
    
    is_disabled = models.BooleanField(default=False)
    reported_at = models.DateTimeField(null=True, blank=True)
    
    created_at = models.DateTimeField(auto_now_add=True)
    modified_at = models.DateTimeField(auto_now=True)
    is_online = models.BooleanField(default=False)
    last_online_at = models.DateTimeField(blank=True, null=True)

    def __str__(self):
        return self.name

    def average_rating(self):
        OrderFeedback = apps.get_model('rampp2p', 'OrderFeedback')
        avg_rating = OrderFeedback.objects.filter(to_peer=self).aggregate(models.Avg('rating'))['rating__avg']
        return avg_rating

    def get_trade_count(self):
        return self.get_orders().count()
    
    def get_orders(self, status=None, annotate_status_info=False):
        Order = apps.get_model('rampp2p', 'Order')
        orders = Order.objects.filter(models.Q(ad_snapshot__ad__owner__id=self.id) | models.Q(owner__id=self.id)) 
        
        if status or annotate_status_info:
            Status = apps.get_model('rampp2p', 'Status')
            # Use a single subquery to get the latest status record
            latest_status_subquery = Status.objects.filter(
                order_id=models.OuterRef('id')
            ).order_by('-created_at')[:1]
            
            orders = orders.annotate(
                latest_status=models.Subquery(latest_status_subquery.values('status')),
                latest_status_created_by=models.Subquery(latest_status_subquery.values('created_by'))
            )
            
            if status:
                orders = orders.filter(latest_status=status)
        return orders
    
    def count_refunded_orders(self):
        refunded_orders = self.get_orders(status='RFN')
        # only count orders appealed by other peers
        refunded_orders = refunded_orders.exclude(appeal__owner__wallet_hash=self.wallet_hash)
        return refunded_orders.count()

    def count_canceled_orders(self):
        canceled_orders = self.get_orders(status='CNCL')
        # only count orders canceled by this peer
        canceled_orders = canceled_orders.filter(latest_status_created_by=self.wallet_hash)
        return canceled_orders.count()

    def count_released_orders(self):
        return self.get_orders(status='RLS').count()

    def get_completed_trades_count(self):
        return self.count_released_orders()

    def get_failed_trades_count(self):
        return self.count_canceled_orders() + self.count_refunded_orders()

    def get_completion_rate(self):
        # completion_rate = released_count / (released_count + canceled_count + refunded_count)
        released_count = self.count_released_orders()
        canceled_count = self.count_canceled_orders()
        refunded_count = self.count_refunded_orders()
        completed_count = released_count + canceled_count + refunded_count
        completion_rate = 0
        if completed_count > 0:
            completion_rate = released_count / completed_count * 100
        return completion_rate
    
    def get_trade_stats(self):
        """Fetch all trade stats in a single query instead of 7+ separate queries."""
        Order = apps.get_model('rampp2p', 'Order')
        Status = apps.get_model('rampp2p', 'Status')
        OrderFeedback = apps.get_model('rampp2p', 'OrderFeedback')

        orders = Order.objects.filter(
            models.Q(ad_snapshot__ad__owner__id=self.id) | models.Q(owner__id=self.id)
        )

        # Annotate with latest status in a single subquery
        latest_status_subquery = Status.objects.filter(
            order_id=models.OuterRef('id')
        ).order_by('-created_at')[:1]

        orders = orders.annotate(
            latest_status=models.Subquery(latest_status_subquery.values('status')),
            latest_status_created_by=models.Subquery(latest_status_subquery.values('created_by'))
        )

        # Single aggregate query for all counts
        stats = orders.aggregate(
            total=models.Count('id'),
            released=models.Count('id', filter=models.Q(latest_status='RLS')),
            canceled=models.Count('id', filter=models.Q(latest_status='CNCL', latest_status_created_by=self.wallet_hash)),
            refunded=models.Count('id', filter=models.Q(latest_status='RFN')) - models.Count(
                'id', filter=models.Q(latest_status='RFN', appeal__owner__wallet_hash=self.wallet_hash)
            ),
        )

        released_count = stats['released']
        canceled_count = stats['canceled']
        refunded_count = max(0, stats['refunded'])
        total = stats['total']
        completed_count = released_count + canceled_count + refunded_count
        completion_rate = 0
        if completed_count > 0:
            completion_rate = released_count / completed_count * 100

        # Rating in a separate simple query (different table)
        avg_rating = OrderFeedback.objects.filter(to_peer=self).aggregate(models.Avg('rating'))['rating__avg']

        return {
            'trade_count': total,
            'completed_trades': released_count,
            'failed_trades': canceled_count + refunded_count,
            'completion_rate': completion_rate,
            'rating': avg_rating,
        }
    
class ReservedName(models.Model):
    peer = models.ForeignKey(Peer, on_delete=models.CASCADE, null=True, blank=True)
    name = models.CharField(max_length=64, unique=True)
    key = models.CharField(max_length=100, unique=True, null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    redeemed_at = models.DateTimeField(null=True, blank=True)

    def __str__(self):
        return self.name

    def save(self, *args, **kwargs):
        if not self.redeemed_at and not self.created_at:
            self.key = get_random_string(24)
        super().save(*args, **kwargs)
