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
    
    created_at = models.DateTimeField(auto_now_add=True)
    modified_at = models.DateTimeField(auto_now=True)
    is_online = models.BooleanField(default=False)
    last_online_at = models.DateTimeField(blank=True, null=True)

    def __str__(self):
        return self.name

    def average_rating(self):
        Feedback = apps.get_model('rampp2p', 'Feedback')
        avg_rating = Feedback.objects.filter(to_peer=self).aggregate(models.Avg('rating'))['rating__avg']
        return avg_rating
    
    def get_orders(self):
        Order = apps.get_model('rampp2p', 'Order')
        return Order.objects.filter(models.Q(ad_snapshot__ad__owner__id=self.id) | models.Q(owner__id=self.id)) 
    
    def get_trade_count(self):
        return self.get_orders().count()
    
    def count_orders_by_status(self, status: str):
        Status = apps.get_model('rampp2p', 'Status')
        latest_status_subquery = Status.objects.filter(order_id=models.OuterRef('id')).order_by('-created_at').values('status')[:1]
        user_orders = self.get_orders().annotate(latest_status=models.Subquery(latest_status_subquery))

        return user_orders.filter(status__status=status).count()
    
    def count_completed_orders(self):
        completed_statuses = ['RLS', 'CNCL', 'RFN']
        total_count = 0
        for status in completed_statuses:
            total_count += self.count_orders_by_status(status)

        return total_count
    
    def count_released_orders(self):
        return self.count_orders_by_status('RLS')
    
    def get_completion_rate(self):
        # completion_rate = released_count / (released_count + canceled_count + refunded_count)
        completed_count = self.count_completed_orders()
        released_count = self.count_released_orders()
        completion_rate = 0
        if completed_count > 0:
            completion_rate = released_count / completed_count * 100
        return completion_rate
        

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
