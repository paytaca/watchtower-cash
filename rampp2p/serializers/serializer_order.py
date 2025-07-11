from PIL import Image
from rest_framework import serializers
from django.db.models import Q

from .serializer_ad import SubsetAdSnapshotSerializer, PublicAdSnapshotSerializer
from .serializer_payment import SubsetPaymentMethodSerializer
from .serializer_transaction import TransactionSerializer
import rampp2p.models as models

import logging
logger = logging.getLogger(__name__)

class PublicOrderSerializer(serializers.ModelSerializer):
    ad_snapshot = PublicAdSnapshotSerializer()
    owner = serializers.SerializerMethodField()
    price = serializers.SerializerMethodField()
    trade_type = serializers.SerializerMethodField()
    status = serializers.SerializerMethodField()
    currency = serializers.SerializerMethodField()

    class Meta:
        model = models.Order
        fields = [
            'id',
            'ad_snapshot',
            'owner',
            'trade_amount',
            'currency',
            'price',
            'trade_type',
            'status',
            'is_cash_in',
        ]
    
    def get_price(self, obj):
        return obj.ad_snapshot.price
         
    def get_owner(self, obj):
        return {
            'id': obj.owner.id,
            'name': obj.owner.name
        }
    
    def get_trade_type(self, obj):
        return obj.trade_type
    
    def get_status(self, obj):
        return {
            'value': obj.status.status,
            'label': obj.status.get_status_display(),
        }
    
    def get_currency(self, obj):
        return obj.currency.symbol

class OrderMemberSerializer(serializers.Serializer):
    id = serializers.IntegerField()
    chat_identity_id = serializers.IntegerField()
    public_key = serializers.CharField()
    name = serializers.CharField()
    address = serializers.CharField()
    is_arbiter = serializers.BooleanField()

class OrderArbiterSerializer(serializers.ModelSerializer):
    class Meta:
        model = models.Arbiter
        fields = ['id', 'name']

class OrderSerializer(serializers.ModelSerializer):
    ad = serializers.SerializerMethodField()
    members = serializers.SerializerMethodField()
    owner = serializers.SerializerMethodField()
    contract  = serializers.SerializerMethodField()
    transactions = serializers.SerializerMethodField()
    arbiter = OrderArbiterSerializer()
    price = serializers.SerializerMethodField()
    trade_type = serializers.SerializerMethodField()
    status = serializers.SerializerMethodField()
    payment_method_opts = serializers.SerializerMethodField()
    payment_methods_selected = serializers.SerializerMethodField()
    last_modified_at = serializers.SerializerMethodField() # lastest order status created_at
    is_ad_owner = serializers.SerializerMethodField()
    feedback = serializers.SerializerMethodField()
    read_at = serializers.SerializerMethodField()
    has_unread_status = serializers.SerializerMethodField()
    
    class Meta:
        model = models.Order
        fields = [
            'id',
            'tracking_id',
            'ad',
            'members',
            'owner',
            'contract',
            'transactions',
            'arbiter',
            'payment_method_opts',
            'payment_methods_selected',
            'trade_amount',
            'price',
            'trade_type',
            'status',
            'is_ad_owner',
            'feedback',
            'chat_session_ref',
            'is_cash_in',
            'created_at',
            'appealable_at',
            'last_modified_at',
            'expires_at',
            'read_at',
            'has_unread_status'
        ]
    
    def get_price(self, obj):
        return obj.ad_snapshot.price

    def get_ad(self, obj):
        serialized_ad_snapshot = SubsetAdSnapshotSerializer(obj.ad_snapshot)
        return serialized_ad_snapshot.data
    
    def get_members(self, obj):
        ad_owner = None
        members = {
            'arbiter': obj.arbiter
        }
        if obj.ad_snapshot.trade_type == models.TradeType.SELL:
            members['seller'] = obj.ad_snapshot.ad.owner
            members['buyer'] = obj.owner
            ad_owner = members['seller']
        else:
            members['seller'] = obj.owner
            members['buyer'] = obj.ad_snapshot.ad.owner
            ad_owner = members['buyer']
            
        for key, member in members.items():
            if members[key] is not None:
                members[key] = {
                    'id': member.id,
                    'chat_identity_id': member.chat_identity_id,
                    'public_key': member.public_key,
                    'name': member.name,
                    'address': member.address,
                    'rating': member.average_rating(),
                    'is_ad_owner': member.wallet_hash == ad_owner.wallet_hash,
                    'is_online': member.is_online,
                    'last_online_at': member.last_online_at
                }
        return members
         
    def get_owner(self, obj):
        return {
            'id': obj.owner.id,
            'name': obj.owner.name,
            'rating': obj.owner.average_rating(),
            'is_online': obj.owner.is_online,
            'last_online_at': obj.owner.last_online_at
        }

    def get_contract(self, obj):
        try:
            contract = models.Contract.objects.get(order=obj)
        except models.Contract.DoesNotExist:
            return None
        return contract.id
    
    def get_transactions(self, obj):
        transactions = models.Transaction.objects.filter(contract__order__id = obj.id)
        serializer = TransactionSerializer(transactions, many=True)
        return serializer.data

    def get_payment_method_opts(self, obj):
        escrowed_status = models.Status.objects.filter(Q(order=obj) & Q(status=models.StatusType.ESCROWED))
        if escrowed_status.exists():            
            serialized_payment_methods = SubsetPaymentMethodSerializer(
                obj.payment_methods.all(), 
                many=True,
                context={'order_id': obj.id}
            )
            payment_methods = serialized_payment_methods.data
            return payment_methods
    
    def get_payment_methods_selected(self, obj):
        order_payments = models.OrderPayment.objects.select_related('payment_method').filter(order_id=obj.id)
        payment_methods = []
        for method in order_payments:
            attachments = models.OrderPaymentAttachment.objects.filter(payment__id=method.id)
            data = SubsetPaymentMethodSerializer(method.payment_method, context={'order_id': obj.id}).data
            data['order_payment_id'] = method.id
            data['attachments'] = OrderPaymentAttachmentSerializer(attachments, many=True).data
            payment_methods.append(data)
        return payment_methods

    def get_latest_order_status(self, obj):
        latest_status = models.Status.objects.filter(Q(order=obj)).last()
        return latest_status
    
    def get_trade_type(self, obj):
        ad_trade_type = obj.ad_snapshot.trade_type
        order_trade_type = models.TradeType.BUY
        if ad_trade_type == models.TradeType.BUY:
            order_trade_type = models.TradeType.SELL
        return order_trade_type
    
    def get_status(self, obj):
        latest_status = self.get_latest_order_status(obj)
        if latest_status is not None:
            latest_status = {
                'label': latest_status.get_status_display(),
                'value': latest_status.status,
                'created_at': latest_status.created_at
            }
        return latest_status
    
    def get_last_modified_at(self, obj):
        last_modified_at = None
        latest_status = models.Status.objects.values('created_at').filter(order__id=obj.id).order_by('-created_at').first()
        if latest_status is not None:
            last_modified_at = str(latest_status['created_at'])
        return last_modified_at
    
    def get_is_ad_owner(self, obj):
        wallet_hash = self.context['wallet_hash']
        if obj.ad_snapshot.ad.owner.wallet_hash == wallet_hash:
            return True
        return False
    
    def get_read_at(self, obj):
        wallet_hash = self.context.get('wallet_hash')
        order_member = models.OrderMember.objects.filter(Q(order__id=obj.id) & (Q(peer__wallet_hash=wallet_hash) | Q(arbiter__wallet_hash=wallet_hash)))
        if order_member.exists():
            read_at = order_member.first().read_at
            return str(read_at) if read_at != None else read_at
        return None

    def get_has_unread_status(self, obj):
        wallet_hash = self.context.get('wallet_hash')
        statuses = models.Status.objects.filter(order__id=obj.id)
        has_unread = False
        if obj.is_seller(wallet_hash):
            has_unread = statuses.filter(seller_read_at__isnull=True).exists()
        else:
            has_unread = statuses.filter(buyer_read_at__isnull=True).exists()
        return has_unread
    
    def get_feedback(self, obj):
        wallet_hash = self.context['wallet_hash']
        status = self.get_status(obj)
        feedback = None
        if status['value'] in ['CNCL', 'RLS', 'RFN']:
            user_feedback = models.OrderFeedback.objects.filter(Q(from_peer__wallet_hash=wallet_hash) and Q(order__id=obj.id)).first()
            if user_feedback:
                feedback = {
                    'id': user_feedback.id,
                    'rating': user_feedback.rating
                }
        return feedback

class WriteOrderSerializer(serializers.ModelSerializer):
    tracking_id = serializers.CharField(required=False)
    ad_snapshot = serializers.PrimaryKeyRelatedField(required=True, queryset=models.AdSnapshot.objects.all())
    owner = serializers.PrimaryKeyRelatedField(required=True, queryset=models.Peer.objects.all())
    arbiter = serializers.PrimaryKeyRelatedField(queryset=models.Arbiter.objects.all(), required=False)
    trade_amount = serializers.IntegerField(required=True)
    payment_methods = serializers.PrimaryKeyRelatedField(queryset=models.PaymentMethod.objects.all(), required=False, many=True)
    is_cash_in = serializers.BooleanField(required=True)

    class Meta:
        model = models.Order
        fields = [
            'tracking_id',
            'ad_snapshot', 
            'owner',
            'arbiter',
            'trade_amount',
            'payment_methods',
            'chat_session_ref',
            'is_cash_in'
        ]

class OrderPaymentSerializer(serializers.ModelSerializer):
    order = serializers.PrimaryKeyRelatedField(required=True, queryset=models.Order.objects.all())
    payment_method = serializers.PrimaryKeyRelatedField(required=True, queryset=models.PaymentMethod.objects.all())
    payment_type = serializers.PrimaryKeyRelatedField(required=True, queryset=models.PaymentType.objects.all())
    attachments = serializers.SerializerMethodField(required=False)

    class Meta:
        model = models.OrderPayment
        fields = [
            'id',
            'order',
            'payment_method',
            'payment_type',
            'attachments'
        ]
    
    def get_attachments(self, obj):
        attachments = models.OrderPaymentAttachment.objects.filter(payment__id=obj.id)
        return OrderPaymentAttachmentSerializer(attachments, many=True).data


class ImageUploadSerializer(serializers.ModelSerializer):
    class Meta:
        model = models.ImageUpload
        fields = ['id', 'url', 'url_path', 'file_hash', 'size']

class OrderPaymentAttachmentSerializer(serializers.ModelSerializer):
    payment = serializers.PrimaryKeyRelatedField(queryset=models.OrderPayment.objects.all())
    image = ImageUploadSerializer()

    class Meta:
        model = models.OrderPaymentAttachment
        fields = ['id', 'payment', 'image']