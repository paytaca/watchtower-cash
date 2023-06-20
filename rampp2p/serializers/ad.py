from rest_framework import serializers
from django.db.models import Q, Subquery, OuterRef, F
from rampp2p.models import (
    Ad, 
    DurationChoices,
    Peer,
    FiatCurrency, 
    CryptoCurrency,
    Order, 
    Status, 
    StatusType,
    PaymentMethod
)
from .currency import FiatCurrencySerializer, CryptoCurrencySerializer
from .payment import RelatedPaymentMethodSerializer

class AdListSerializer(serializers.ModelSerializer):
    owner = serializers.SlugRelatedField(slug_field="nickname", queryset=Peer.objects.all())
    fiat_currency = FiatCurrencySerializer()
    crypto_currency = CryptoCurrencySerializer()
    payment_methods = RelatedPaymentMethodSerializer(many=True)
    trade_count = serializers.SerializerMethodField()
    completion_rate = serializers.SerializerMethodField()

    class Meta:
        model = Ad
        fields = [
        'id',
        'owner',
        'trade_type',
        'fiat_currency',
        'crypto_currency',
        'fixed_price',
        'floating_price',
        'trade_floor',
        'trade_ceiling',
        'crypto_amount',
        'payment_methods',
        'trade_count',
        'completion_rate',
        ]
    
    def get_trade_count(self, instance: Ad):
        # Count the number of trades (orders) related to ad owner
        query = Q(ad__owner__id=instance.owner.id)
        trade_count = Order.objects.filter(query).count()
        return trade_count

    def get_completion_rate(self, instance: Ad):
        ''' 
        completion_rate = released_count / (released_count + canceled_count + refunded_count)
        '''
        
        owner_id = instance.owner.id
        released_count = self.get_orders_status_count(owner_id, StatusType.RELEASED)
        canceled_count = self.get_orders_status_count(owner_id, StatusType.CANCELED)
        refunded_count = self.get_orders_status_count(owner_id, StatusType.REFUNDED)
        
        completion_rate = 0
        denum = released_count + canceled_count + refunded_count        
        if denum > 0:
            completion_rate = released_count / denum * 100
        
        return completion_rate
    
    def get_orders_status_count(self, owner_id: int, status: StatusType):
        # Subquery to get the latest status for each order
        query = Q(order_id=OuterRef('id')) & Q(status=status)
        latest_status_subquery = Status.objects.filter(query).order_by('-created_at').values('id')[:1]
        
        # Retrieve the latest statuses for each order
        user_orders = Order.objects.filter(Q(ad__owner__id=owner_id)).annotate(
            latest_status_id = Subquery(latest_status_subquery)
        )

        # Filter only the orders with their latest status
        filtered_orders_count = user_orders.filter(status__id=F('latest_status_id')).count()
        return filtered_orders_count

class AdWriteSerializer(serializers.ModelSerializer):
    owner = serializers.PrimaryKeyRelatedField(queryset=Peer.objects.all())
    fiat_currency = serializers.PrimaryKeyRelatedField(queryset=FiatCurrency.objects.all())
    crypto_currency = serializers.PrimaryKeyRelatedField(queryset=CryptoCurrency.objects.all())
    payment_methods = serializers.PrimaryKeyRelatedField(queryset=PaymentMethod.objects.all(), many=True)
    time_duration_choice = serializers.ChoiceField(choices=DurationChoices.choices,required=True)
    class Meta:
        model = Ad
        fields = [
            'id',
            'owner',
            'trade_type',
            'price_type',
            'fiat_currency',
            'crypto_currency',
            'fixed_price',
            'floating_price',
            'trade_floor',
            'trade_ceiling',
            'crypto_amount',
            'time_duration_choice',
            'payment_methods',
            'modified_at',
        ]
        read_only_fields = [
        'owner',
        'fiat_currency',
        'crypto_currency',
        'payment_methods',
        ]
        depth = 1