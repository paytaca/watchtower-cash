from rest_framework import status, viewsets
from rest_framework.response import Response
from rest_framework.decorators import action

from django.http import Http404
from django.utils import timezone
from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.db.models import Q, OuterRef, Subquery, Case, When, Value, BooleanField, CharField

from decimal import Decimal
from datetime import datetime, time, timedelta
from typing import List
import math

from authentication.token import TokenAuthentication
from authentication.permissions import RampP2PIsAuthenticated

import rampp2p.models as models
import rampp2p.serializers as serializers
import rampp2p.utils.utils as utils
import rampp2p.utils.websocket as websocket
from rampp2p.utils import satoshi_to_bch, bch_to_fiat

from rampp2p.utils.notifications import send_push_notification
from rampp2p.viewcodes import WSGeneralMessageType
from rampp2p.validators import *

import logging
logger = logging.getLogger(__name__)

class CashinOrderViewSet(viewsets.GenericViewSet):
    queryset = models.Order.objects.all()

    @action(detail=False, methods=['get'])
    def list(self, request):
        wallet_hash = request.query_params.get('wallet_hash')
        status_type = request.query_params.get('status_type')
        owned = request.query_params.get('owned')
        if owned is not None:
            owned = owned == 'true'

        try:
            limit = int(request.query_params.get('limit', 10))
            page = int(request.query_params.get('page', 1))
            if limit < 0:
                raise ValidationError('limit must be a non-negative number')
            if page < 1:
                raise ValidationError('invalid page number')
        except (ValueError, ValidationError) as err:
            return Response({'error': err.args[0]}, status=status.HTTP_400_BAD_REQUEST)

        queryset = models.Order.objects.filter(is_cash_in=True)
        
        # exclude completed orders
        completed_status = [
            StatusType.CANCELED,
            StatusType.RELEASED,
            StatusType.REFUNDED
        ]
        last_status_subq = Status.objects.filter(
            order=OuterRef('pk')
        ).order_by('-created_at').values('status')[:1]
        queryset = queryset.annotate(last_status=Subquery(last_status_subq))

        if status_type == 'ONGOING':
            queryset = queryset.exclude(last_status__in=completed_status)
        if status_type == 'COMPLETED':
            queryset = queryset.exclude(last_status__in=completed_status)
        
        # fetches orders created by user
        owned_orders = Q(owner__wallet_hash=wallet_hash)

        if not owned:
            # fetches the orders that have ad ids owned by user
            ad_orders = Q(ad_snapshot__ad__pk__in=list(
                            # fetches the flat ids of ads owned by user
                            models.Ad.objects.filter(
                                owner__wallet_hash=wallet_hash
                            ).values_list('id', flat=True)
                        ))

            queryset = queryset.filter(owned_orders | ad_orders)
        else:
            queryset = queryset.filter(owned_orders)

        queryset = queryset.order_by('-created_at')
        
        # Count total pages
        count = queryset.count()
        total_pages = page
        if limit > 0:
            total_pages = math.ceil(count / limit)

        # Splice queryset
        offset = (page - 1) * limit
        page_results = queryset[offset:offset + limit]

        context = { 'wallet_hash': wallet_hash }
        serializer = serializers.OrderSerializer(page_results, many=True, context=context)
        data = {
            'orders': serializer.data,
            'count': count,
            'total_pages': total_pages
        }
        return Response(data, status.HTTP_200_OK)

    @action(detail=False, methods=['get'])
    def check_alerts(self, request):
        wallet_hash = request.query_params.get('wallet_hash')
        has_cashin_alerts = utils.check_has_cashin_alerts(wallet_hash)
        return Response({'has_cashin_alerts': has_cashin_alerts}, status=200)

class OrderViewSet(viewsets.GenericViewSet):
    authentication_classes = [TokenAuthentication]
    permission_classes = [RampP2PIsAuthenticated]
    queryset = models.Order.objects.all()

    def retrieve(self, request, pk):
        try:
            order = self.get_queryset().get(pk=pk)
        except models.Order.DoesNotExist:
            raise Http404
        
        wallet_hash = request.headers.get('wallet_hash')
        if wallet_hash is None:
            return Response({'error': 'wallet_hash is required'}, status=status.HTTP_400_BAD_REQUEST)
        
        serialized_order = serializers.OrderSerializer(order, context={ 'wallet_hash': wallet_hash }).data
        
        if serialized_order['status']['value'] == StatusType.APPEALED:
            appeal = models.Appeal.objects.filter(order_id=order.id)
            if appeal.exists():
                serialized_appeal = serializers.AppealSerializer(appeal.first()).data
                serialized_order['appeal'] = serialized_appeal
        return Response(serialized_order, status=status.HTTP_200_OK)

    def list(self, request):
        wallet_hash = request.user.wallet_hash
        params = self.parse_params(request)

        if params['status_type'] is None:
            return Response(
                {'error': 'status_type is required'},
                status=status.HTTP_400_BAD_REQUEST
            )

        try:
            limit = int(params['limit'])
            page = int(params['page'])
            if limit < 0:
                raise ValidationError('limit must be a non-negative number')
            if page < 1:
                raise ValidationError('invalid page number')
        except (ValueError, ValidationError) as err:
            return Response({'error': err.args[0]}, status=status.HTTP_400_BAD_REQUEST)

        queryset = models.Order.objects.all()

        # fetches orders created by user
        owned_orders = Q(owner__wallet_hash=wallet_hash)

        # fetches the orders that have ad ids owned by user
        ad_orders = Q(ad_snapshot__ad__pk__in=list(
                        # fetches the flat ids of ads owned by user
                        models.Ad.objects.filter(
                            owner__wallet_hash=wallet_hash
                        ).values_list('id', flat=True)
                    ))

        if params['owned'] == True:
            queryset = queryset.filter(owned_orders)
        elif params['owned'] == False:
            queryset = queryset.filter(ad_orders)
        else:
            queryset = queryset.filter(owned_orders | ad_orders)

        # filter by currency
        if params['currency']:
            queryset = queryset.filter(ad_snapshot__fiat_currency__symbol=params['currency'])

        # filter or exclude orders based to their latest status
        completed_status = [
            StatusType.CANCELED,
            StatusType.RELEASED,
            StatusType.REFUNDED
        ]
        last_status_subq = Status.objects.filter(
            order=OuterRef('pk')
        ).order_by('-created_at').values('status')[:1]
        queryset = queryset.annotate(last_status=Subquery(last_status_subq))

        if params['status_type'] == 'COMPLETED':            
            queryset = queryset.filter(last_status__in=completed_status)
        elif params['status_type'] == 'ONGOING':
            queryset = queryset.exclude(is_cash_in=True)
            queryset = queryset.exclude(last_status__in=completed_status)
        
        if len(params['statuses']) > 0:
            # get the order's last status
            last_status_subq = models.Status.objects.filter(order=OuterRef('id')).order_by('-created_at').values('status')[:1]
            # check if the last status is a subset of filtered statuses
            temp = queryset.annotate(
                last_status=Subquery(last_status_subq)
                ).annotate(
                    is_in_filtered_status = Case(
                        When(last_status__in=list(map(str, params['statuses'])), then=Value(True)),
                        default=Value(False),
                        output_field=BooleanField(),
                    )                    
                )
            queryset = temp.filter(is_in_filtered_status=True)

        # filters by ad payment types
        if len(params['payment_types']) > 0:
            payment_types = list(map(int, params['payment_types']))
            queryset = queryset.filter(Q(ad_snapshot__payment_types__id__in=payment_types) | Q(ad_snapshot__payment_types=None)).distinct()

        # filters by ad time limits
        if len(params['time_limits']) > 0:
            time_limits = list(map(int, params['time_limits']))
            queryset = queryset.filter(ad_snapshot__appeal_cooldown_choice__in=time_limits).distinct()

        # filters by order trade type
        if params['trade_type'] is not None:
            queryset = queryset.exclude(Q(ad_snapshot__trade_type=params['trade_type']))

        # filter/exclude appealable orders
        filter = not(params['appealable'] and params['not_appealable'] )
        if filter is True:
            if params['appealable'] is True:
                queryset = queryset.filter(Q(appealable_at__isnull=False))
                queryset = queryset.exclude(last_status=StatusType.APPEALED)
            if params['not_appealable'] is True:
                queryset = queryset.exclude(Q(appealable_at__isnull=False))

        if params['sort_by'] == 'last_modified_at':
            sort_field = 'last_modified_at'
            if params['sort_type'] == 'descending':
                sort_field = f'-{sort_field}'
            last_status_created_at = models.Status.objects.filter(
                order=OuterRef('pk')).order_by('-created_at').values('created_at')[:1]
            queryset = queryset.annotate(
                last_modified_at=Subquery(last_status_created_at)
            ).order_by(sort_field)
        else:
            sort_field = 'created_at'
            if (params['sort_type'] == 'descending'):
                sort_field = f'-{sort_field}'
            if params['status_type'] == 'ONGOING':
                queryset = queryset.order_by(sort_field)
            if params['status_type'] == 'COMPLETED':
                queryset = queryset.order_by(sort_field)
                
        # search for orders with specific owner name
        if params['query_name']:
            queryset = queryset.filter(owner__name__icontains=params['query_name'])

        # Count total pages
        count = queryset.count()
        total_pages = page
        if limit > 0:
            total_pages = math.ceil(count / limit)

        # Splice queryset
        offset = (page - 1) * limit
        page_results = queryset[offset:offset + limit]

        context = { 'wallet_hash': wallet_hash }
        serializer = serializers.OrderSerializer(page_results, many=True, context=context)
        unread_count = models.OrderMember.objects.filter(Q(peer__wallet_hash=wallet_hash) & Q(read_at__isnull=True)).count()
        data = {
            'orders': serializer.data,
            'count': count,
            'total_pages': total_pages,
            'unread_count': unread_count
        }
        return Response(data, status.HTTP_200_OK)

    def create(self, request):
        wallet_hash = request.user.wallet_hash
        try:
            payment_method_ids = request.data.get('payment_methods', [])
            is_cash_in = request.data.get('is_cash_in', False)
            trade_amount = request.data.get('trade_amount')
            if trade_amount == None or trade_amount == 0:
                raise ValidationError('trade_amount field is required')

            ad = models.Ad.objects.get(pk=request.data.get('ad'))
            owner = models.Peer.objects.get(wallet_hash=wallet_hash)

            # require payment methods if creating a SELL order
            if ad.trade_type == models.TradeType.BUY:
                if len(payment_method_ids) == 0:
                    raise ValidationError('payment_methods field is required for SELL orders')            
                self.check_payment_permissions(wallet_hash, payment_method_ids)
            
            # check permissions
            self.check_create_permissions(wallet_hash, ad.id)
        
            with transaction.atomic():
                if is_cash_in:
                    self.require_singular_cashin_order(wallet_hash=wallet_hash)

                snapshot = self.snapshot_ad(ad)
                tracking_id = self.generate_tracking_id()

                data = {
                    'owner': owner.id,
                    'ad_snapshot': snapshot.id,
                    'payment_methods': payment_method_ids,
                    'trade_amount': trade_amount,
                    'is_cash_in': is_cash_in,
                    'tracking_id': tracking_id
                }
                serialized_order = serializers.WriteOrderSerializer(data=data)
                serialized_order.is_valid(raise_exception=True)
                order = serialized_order.save()
                
                self.set_expiration_date(order)
                self.submit_order(ad=ad, order=order, wallet_hash=wallet_hash)

                members = self.create_members(snapshot=snapshot, order=order)
                self.mark_creator_as_read(order=order, members=members)

                if order.is_cash_in:
                    self.create_order_payment_methods(payment_method_ids=payment_method_ids, order=order)

                self.update_ad_trade_amount(order=order)
                serialized_status = self.confirm_order(wallet_hash=wallet_hash, order=order)

                serialized_order = serializers.OrderSerializer(order, context={'wallet_hash': wallet_hash}).data    
                response = {
                    'success': True,
                    'order': serialized_order,
                    'status': serialized_status
                }
            return Response(response, status=status.HTTP_201_CREATED)
        except (models.Ad.DoesNotExist, models.Peer.DoesNotExist, ValidationError) as err:
            return Response({'error': err.args[0]}, status=status.HTTP_400_BAD_REQUEST)

    def partial_update(self, request, pk):
        try:
            order = self.get_queryset().get(pk=pk)
        except models.Order.DoesNotExist:
            raise Http404

        wallet_hash = request.user.wallet_hash
        chat_session_ref = request.data.get('chat_session_ref')

        if chat_session_ref:
            order.chat_session_ref = chat_session_ref
            order.save()

        serialized_order = serializers.OrderSerializer(order, context={ 'wallet_hash': wallet_hash }).data
        return Response(serialized_order, status=status.HTTP_200_OK)

    @action(detail=True, methods=['get'])
    def members(self, request, pk):
        if request.method == 'GET':
            try:
                order = models.Order.objects.get(pk=pk)
                members = [order.owner, order.ad_snapshot.ad.owner]
                if order.arbiter:
                    members.append(order.arbiter)

                member_info = []
                for member in members:
                    member_info.append({
                        'id': member.id,
                        'chat_identity_id': member.chat_identity_id,
                        'public_key': member.public_key,
                        'name': member.name,
                        'address': member.address,
                        'is_arbiter': isinstance(member, models.Arbiter)
                    })
                
                members = serializers.OrderMemberSerializer(member_info, many=True)
            except models.Order.DoesNotExist:
                raise Http404
            except Exception as err:
                return Response({'error': err.args[0]}, status=status.HTTP_400_BAD_REQUEST)
            return Response(members.data, status=status.HTTP_200_OK)
        
        if request.method == 'PATCH':
            wallet_hash = request.user.wallet_hash
            member = models.OrderMember.objects.filter(Q(order__id=pk) & (Q(peer__wallet_hash=wallet_hash) | Q(arbiter__wallet_hash=wallet_hash)))
            if not member.exists():
                return Response({'success': False, 'error': 'no such member'}, status=status.HTTP_400_BAD_REQUEST)
            
            member = member.first()
            member.read_at = timezone.now()
            member.save()
        
            if isinstance(request.user, models.Arbiter):
                member_orders = models.OrderMember.objects.filter(Q(read_at__isnull=True) & Q(arbiter__wallet_hash=wallet_hash)).values_list('order', flat=True)
                unread_count = models.Appeal.objects.filter(order__in=member_orders).count()
            else:
                unread_count = models.OrderMember.objects.filter(Q(read_at__isnull=True) & Q(peer__wallet_hash=wallet_hash)).count()
            
            websocket.send_general_update({'type': WSGeneralMessageType.READ_ORDER.value, 'extra': { 'unread_count': unread_count }}, wallet_hash)
            return Response({'success': True}, status=status.HTTP_200_OK)
    
    def parse_params(self, request_data):
        request = request_data
        limit = request.query_params.get('limit', 0)
        page = request.query_params.get('page', 1)
        status_type = request.query_params.get('status_type')
        currency = request.query_params.get('currency')
        trade_type = request.query_params.get('trade_type')
        statuses = request.query_params.getlist('status')
        payment_types = request.query_params.getlist('payment_types')
        time_limits = request.query_params.getlist('time_limits')
        sort_by = request.query_params.get('sort_by')
        sort_type = request.query_params.get('sort_type')
        owned = request.query_params.get('owned')
        appealable = request.query_params.get('appealable')
        not_appealable = request.query_params.get('not_appealable')
        query_name = request.query_params.get('query_name')

        if owned is not None:
            owned = owned == 'true'
        if appealable is not None:
            appealable = appealable == 'true'
        if not_appealable is not None:
            not_appealable = not_appealable == 'true'

        return {
            'limit': limit,
            'page': page,
            'status_type': status_type,
            'currency': currency,
            'trade_type': trade_type,
            'statuses': statuses,
            'payment_types': payment_types,
            'time_limits': time_limits,
            'sort_by': sort_by,
            'sort_type': sort_type,
            'owned': owned,
            'appealable': appealable,
            'not_appealable': not_appealable,
            'query_name': query_name
        }
    
    def generate_tracking_id(self):
        ''' PEO[year][month][day]-[order_count_today] e.g. PEO20211201-0001 '''
        today = datetime.today()
        today_midnight = datetime.combine(today, time.min)
        next_day_midnight = datetime.combine(today + timedelta(days=1), time.min)
        order_count = models.Order.objects.filter(created_at__gte=today_midnight, created_at__lt=next_day_midnight).count()
        tracking_id = f'PEO{today.year}{str(today.month).zfill(2)}{str(today.day).zfill(2)}-{str(order_count).zfill(4)}'
        return tracking_id
    
    def check_create_permissions(self, wallet_hash, pk):
        '''
        - Arbiters are not allowed to create orders
        - Ad owners are not allowed to create orders for their own ads
        '''
        # check if arbiter
        is_arbiter = models.Arbiter.objects.filter(wallet_hash=wallet_hash).exists()
        if is_arbiter: raise ValidationError('Arbiter cannot create orders')

        # check if ad owner
        is_ad_owner = models.Ad.objects.filter(pk=pk, owner__wallet_hash=wallet_hash).exists()
        if is_ad_owner: raise ValidationError('Ad owner cannot create order for this ad')

    def check_payment_permissions(self, wallet_hash, payment_method_ids: List[int]):
        ''' Validates if peer owns the payment methods '''
        owned_payment_methods = models.PaymentMethod.objects.filter(Q(owner__wallet_hash=wallet_hash) & Q(id__in=payment_method_ids))
        if len(payment_method_ids) != owned_payment_methods.count():
            raise ValidationError(f'Invalid payment method(s). Expected {len(payment_method_ids)} owned payment methods, got {owned_payment_methods.count()}.')
    
    def cancellable_cash_in_orders(self, wallet_hash):
        queryset = models.Order.objects.filter(Q(owner__wallet_hash=wallet_hash) & Q(is_cash_in=True))

        latest_status = models.Status.objects.filter(order__id=OuterRef('pk')).order_by('-id')
        queryset = queryset.annotate(
            latest_status = Subquery(latest_status.values('status')[:1], output_field=CharField())
        )
        queryset = queryset.filter(Q(latest_status=StatusType.SUBMITTED) | Q(latest_status=StatusType.CONFIRMED)).values_list('id', flat=True)
        return queryset

    def update_ad_trade_amount(self, order=None):
        # Decrease the Ad's trade amount and ceiling
        ad = order.ad_snapshot.ad
        if order.ad_snapshot.trade_limits_in_fiat:
            order_amount_fiat = bch_to_fiat(satoshi_to_bch(order.trade_amount), order.ad_snapshot.price)
            ad_quantity_fiat = Decimal(order.ad_snapshot.trade_amount_fiat)
            new_ad_quantity_fiat = ad_quantity_fiat - order_amount_fiat
            
            if new_ad_quantity_fiat < 0:
                raise ValidationError('order amount exceeds ad remaining trade quantity')
            
            ad.trade_amount_fiat = new_ad_quantity_fiat
            if ad.trade_amount_fiat < ad.trade_ceiling_fiat:
                ad.trade_ceiling_fiat = new_ad_quantity_fiat
        else:
            order_amount_sats = order.trade_amount
            ad_quantity_sats = order.ad_snapshot.ad.trade_amount_sats
            new_ad_quantity_sats = ad_quantity_sats - order_amount_sats
            
            if new_ad_quantity_sats < 0:
                raise ValidationError('order amount exceeds ad remaining trade quantity')
            
            ad.trade_amount_sats = new_ad_quantity_sats
            if ad.trade_amount_sats < ad.trade_ceiling_sats:
                ad.trade_ceiling_sats = new_ad_quantity_sats
        ad.save()

    def get_market_price(self, currency):
        market_price = models.MarketPrice.objects.filter(currency=currency)
        if not market_price.exists():
            raise ValidationError(f'market price for currency {currency} does not exist.')
        return market_price.first()
    
    def snapshot_ad(self, ad):
        # query market price for ad fiat currency
        market_price = self.get_market_price(ad.fiat_currency.symbol)

        ad_snapshot = models.AdSnapshot(
            ad = ad,
            trade_type = ad.trade_type,
            price_type = ad.price_type,
            fiat_currency = ad.fiat_currency,
            crypto_currency = ad.crypto_currency,
            fixed_price = ad.fixed_price,
            floating_price = ad.floating_price,
            market_price = market_price.price,
            trade_floor_sats = ad.trade_floor_sats,
            trade_ceiling_sats = ad.trade_ceiling_sats,
            trade_amount_sats = ad.trade_amount_sats,
            trade_floor_fiat = ad.trade_floor_fiat,
            trade_ceiling_fiat = ad.trade_ceiling_fiat,
            trade_amount_fiat = ad.trade_amount_fiat,
            appeal_cooldown_choice = ad.appeal_cooldown_choice,
            trade_amount_in_fiat = ad.trade_amount_in_fiat,
            trade_limits_in_fiat = ad.trade_limits_in_fiat
        )
        ad_snapshot.save()
        ad_payment_methods = ad.payment_methods.all()
        ad_payment_types = [pm.payment_type for pm in ad_payment_methods]
        ad_snapshot.payment_types.set(ad_payment_types)
        return ad_snapshot
    
    def set_expiration_date(self, order):
        expiration = order.created_at + timedelta(hours=24)
        if order.is_cash_in:
            expiration = order.created_at + timedelta(minutes=15)
        order.expires_at = expiration
        order.save()

    def create_status(self, order=None, status_type=None, creator=None):
        submitted_status = serializers.StatusSerializer(data={
            'status': status_type, 
            'order': order.id,
            'created_by': creator
        })
        submitted_status.is_valid(raise_exception=True)
        submitted_status = submitted_status.save()
        return submitted_status
    
    def create_members(self, snapshot=None, order=None):
       
        seller, buyer = None, None
        if snapshot.trade_type == models.TradeType.SELL:
            seller = snapshot.ad.owner
            buyer = order.owner
        else:
            seller = order.owner
            buyer = snapshot.ad.owner
        
        seller_member = models.OrderMember.objects.create(order=order, peer=seller, type=models.OrderMember.MemberType.SELLER)
        buyer_member = models.OrderMember.objects.create(order=order, peer=buyer, type=models.OrderMember.MemberType.BUYER)
        
        return {
            'seller_member': seller_member,
            'buyer_member': buyer_member
        }
    
    def mark_creator_as_read(self, order=None, members=None):
        if members == None or order == None:
            raise ValidationError('mark_creator_as_read: has empty order or members')
        
        seller = members.get('seller_member')
        buyer = members.get('buyer_member')

        # Mark order creator member as already read
        if seller.peer.wallet_hash == order.owner.wallet_hash:
            seller.read_at = timezone.now()
            seller.save()
        
        if buyer.peer.wallet_hash == order.owner.wallet_hash:
            buyer.read_at = timezone.now()
            buyer.save()

    def create_order_payment_methods(self, payment_method_ids=[], order=None):
        payment_methods = models.PaymentMethod.objects.filter(id__in=payment_method_ids)
        for payment_method in payment_methods:
            data = {
                "order": order.id,
                "payment_method": payment_method.id,
                "payment_type": payment_method.payment_type.id
            }
            order_method = serializers.OrderPaymentSerializer(data=data)
            if order_method.is_valid():
                order_method.save()
    
    def require_singular_cashin_order(self, wallet_hash=None):
        cancellable_cashin_orders = self.cancellable_cash_in_orders(wallet_hash)
        if cancellable_cashin_orders.count() > 0:
            raise ValidationError({ 'pending_orders': cancellable_cashin_orders })
    
    def notify_ad_owner_channel(self, ad=None, order=None):
        unread_count = models.OrderMember.objects.filter(Q(read_at__isnull=True) & Q(peer__wallet_hash=ad.owner.wallet_hash)).count()
        serialized_order = serializers.OrderSerializer(order, context={'wallet_hash': ad.owner.wallet_hash})
        websocket.send_general_update({
            'type': WSGeneralMessageType.NEW_ORDER.value,
            'extra': {
                'order': serialized_order.data,
                'unread_count': unread_count
            }
        }, ad.owner.wallet_hash)

    def submit_order(self, ad=None, order=None, wallet_hash=None):
        status = self.create_status(order=order, status_type=StatusType.SUBMITTED, creator=wallet_hash)   
        serialized_status = serializers.StatusReadSerializer(status)

        send_push_notification([ad.owner.wallet_hash], "Received a new order", extra={'order_id': order.id})
        self.notify_ad_owner_channel(ad=ad, order=order)

        return serialized_status.data

    def confirm_order(self, order=None, wallet_hash=None):
        status = self.create_status(order=order, status_type=StatusType.CONFIRMED, creator=wallet_hash)   
        serialized_status = serializers.StatusReadSerializer(status)

        websocket.send_order_update({'success': True, 'status': serialized_status.data}, order.id)
        if order.is_cash_in:
            websocket.send_cashin_order_alert({'type': 'ORDER_STATUS_UPDATED', 'order': order.id}, order.owner.wallet_hash)
        
        send_push_notification(
            [order.owner.wallet_hash],
            f'Order #{order.id} confirmed',
            extra={'order_id': order.id}
        )
        return serialized_status.data

        
class OrderStatusViewSet(viewsets.GenericViewSet):
    authentication_classes = [TokenAuthentication]
    permission_classes = [RampP2PIsAuthenticated]
    serializer_class = serializers.OrderSerializer
    queryset = models.Order.objects.all()

    @action(detail=True, methods=['get'])
    def list_status(self, request, pk):
        queryset = Status.objects.filter(order__id=pk).order_by('-created_at')
        serializer = serializers.StatusSerializer(queryset, many=True)
        return Response(serializer.data, status=status.HTTP_200_OK)

    @action(detail=True, methods=['patch'])
    def read_status(self, request, pk):
        try:
            order = models.Order.objects.get(id=pk)
            member = self._check_status_edit_permissions(order, request.user.wallet_hash)
            statuses = models.Status.objects.filter(order__id=pk)

            status_id = request.data.get('status_id')
            if status_id:
                statuses = statuses.filter(id=status_id)
                
            for status_obj in statuses:
                if member.type == models.OrderMember.MemberType.SELLER:
                    status_obj.seller_read_at = timezone.now()
                if member.type == models.OrderMember.MemberType.BUYER:
                    status_obj.buyer_read_at = timezone.now()
                status_obj.save()
            return Response(status=status.HTTP_200_OK)
        except (ValidationError, models.Order.DoesNotExist) as err:
            return Response({'error': err.args[0]}, status=status.HTTP_400_BAD_REQUEST)
    
    @action(detail=False, methods=['patch'])
    def read_order_status(self, request):
        wallet_hash = request.user.wallet_hash
        order_ids = request.data.get('order_ids', [])
        statuses = models.Status.objects.filter(order__id__in=order_ids)
        for status in statuses:
            if not status.buyer_read_at:
                status.buyer_read_at = timezone.now()
                status.save()

        has_cashin_alerts = utils.check_has_cashin_alerts(wallet_hash)
        return Response({'has_cashin_alerts': has_cashin_alerts}, status=200)
    
    @action(detail=True, methods=['post'])
    def confirm(self, request, pk):
        wallet_hash = request.user.wallet_hash
        try:
            with transaction.atomic():                
                validate_status(pk, StatusType.SUBMITTED)
                validate_status_inst_count(StatusType.CONFIRMED, pk)
                validate_status_progression(StatusType.CONFIRMED, pk)

                order = models.Order.objects.get(pk=pk)
                if order.expires_at and order.expires_at < timezone.now():
                    raise ValidationError('Cannot confirm expired order')
                
                order.save()

        except (ValidationError, IntegrityError, models.Order.DoesNotExist, models.Ad.DoesNotExist) as err:
            return Response({'error': err.args[0]}, status=status.HTTP_400_BAD_REQUEST)
        
        serialized_status = serializers.StatusSerializer(data={
            'status': StatusType.CONFIRMED,
            'order': pk,
            'created_by': wallet_hash
        })

        if not serialized_status.is_valid():
            return Response(serialized_status.errors, status=status.HTTP_400_BAD_REQUEST)
        
        serialized_status = serializers.StatusReadSerializer(serialized_status.save())
        
        # send websocket notification
        websocket.send_order_update({'success': True, 'status': serialized_status.data}, pk)
        if order.is_cash_in:
            websocket.send_cashin_order_alert({'type': 'ORDER_STATUS_UPDATED', 'order': pk}, order.owner.wallet_hash)
        
        # send push notification
        message = f'Order #{order.id} confirmed'
        send_push_notification([order.owner.wallet_hash], message, extra={'order_id': order.id})
        
        return Response(serialized_status.data, status=status.HTTP_200_OK)

    @action(detail=True, methods=['post'])
    def cancel(self, request, pk):
        '''Cancels an order. Is callable by the order or ad owner.'''

        wallet_hash = request.user.wallet_hash

        try:
            order = models.Order.objects.get(pk=pk)
        
            # Caller must be order or ad owner
            order_owner = order.owner.wallet_hash
            ad_owner = order.ad_snapshot.ad.owner.wallet_hash
            if wallet_hash != order_owner and wallet_hash != ad_owner:
                raise ValidationError('Caller must be order or ad owner')

            validate_status_inst_count(StatusType.CANCELED, pk)
            validate_status_progression(StatusType.CANCELED, pk)

            with transaction.atomic():
                # Create CANCELED status for order
                serializer = serializers.StatusSerializer(data={
                    'status': StatusType.CANCELED, 
                    'order': pk,
                    'created_by': wallet_hash
                })
                if not serializer.is_valid():
                    raise ValidationError(serializer.errors)
                serialized_status = serializers.StatusReadSerializer(serializer.save())

                # Mark order as read by all parties
                members = order.members.all()
                for member in members:
                    member.read_at = timezone.now()
                    member.save()

                counterparty = order.get_buyer()
                if counterparty.wallet_hash == wallet_hash:
                    counterparty = order.get_seller()

                send_push_notification([counterparty.wallet_hash], f"Order #{order.id} cancelled", extra={'order_id': order.id})

                # Send WebSocket update
                websocket.send_order_update({'success' : True, 'status': serialized_status.data}, pk)
                if order.is_cash_in:
                    websocket.send_cashin_order_alert({'type': 'ORDER_STATUS_UPDATED', 'order': pk}, order.owner.wallet_hash)

        except ValidationError as err:
            return Response({'error': err.args[0]}, status=status.HTTP_400_BAD_REQUEST)
        return Response(serialized_status.data, status=status.HTTP_200_OK)        

    @action(detail=True, methods=['post'])
    def pending_escrow(self, request, pk):
        '''Creates a status ESCROW_PENDING for a given order. Callable only by the order's seller.'''

        wallet_hash = request.user.wallet_hash
        try:
            order = models.Order.objects.get(pk=pk)        
            
            # Require user is seller
            seller = None
            if order.ad_snapshot.trade_type == models.TradeType.SELL:
                seller = order.ad_snapshot.ad.owner
            else:
                seller = order.owner
            if wallet_hash != seller.wallet_hash:
                raise ValidationError('Caller must be seller.')

            validate_status(pk, StatusType.CONFIRMED)
            validate_status_inst_count(StatusType.ESCROW_PENDING, pk)
            validate_status_progression(StatusType.ESCROW_PENDING, pk)

            contract = models.Contract.objects.get(order__id=pk)
            
            # Create ESCROW_PENDING status for order
            status_serializer = serializers.StatusSerializer(data={
                'status': StatusType.ESCROW_PENDING, 
                'order': pk,
                'created_by': wallet_hash
            })
            if status_serializer.is_valid():
                status_serializer = serializers.StatusReadSerializer(status_serializer.save())
            else: 
                raise ValidationError(f"Encountered error saving status for order#{pk}")

            # Create ESCROW transaction
            transaction, _ = models.Transaction.objects.get_or_create(contract=contract, action=models.Transaction.ActionType.ESCROW)

            # Notify order WebSocket subscribers
            websocket_msg = {
                'success' : True,
                'status': status_serializer.data,
                'transaction': serializers.TransactionSerializer(transaction).data
            }
            websocket.send_order_update(websocket_msg, pk)
            if order.is_cash_in:
                websocket.send_cashin_order_alert({'type': 'ORDER_STATUS_UPDATED', 'order': pk}, order.owner.wallet_hash)

            response = websocket_msg
        except (ValidationError, IntegrityError, models.Contract.DoesNotExist) as err:
            return Response({'error': err.args[0]}, status=status.HTTP_400_BAD_REQUEST)

        return Response(response, status=status.HTTP_200_OK)  

    @action(detail=True, methods=['post'])
    def buyer_confirm_payment(self, request, pk):
        wallet_hash = request.user.wallet_hash
        try:
            order = models.Order.objects.get(pk=pk)

            # Only buyers can set order status to PAID_PENDING
            buyer = None
            if order.ad_snapshot.trade_type == models.TradeType.SELL:
                buyer = order.owner
            else:
                buyer = order.ad_snapshot.ad.owner

            if wallet_hash != buyer.wallet_hash:
                raise ValidationError('Caller must be buyer')

            validate_status_inst_count(StatusType.PAID_PENDING, pk)
            validate_status_progression(StatusType.PAID_PENDING, pk)

            response = {}
            order_payment_methods = []
            if not order.is_cash_in:
                '''Require selected payment methods if order is not cash-in.
                Cash-in orders already have payment methods selected on order creation'''

                payment_method_ids = request.data.get('payment_methods')
                if payment_method_ids is None or len(payment_method_ids) == 0:
                    raise ValidationError('Field payment_methods is required')
                
                # Update order payment methods to selected payment methods
                payment_methods = models.PaymentMethod.objects.filter(id__in=payment_method_ids)
                order.payment_methods.add(*payment_methods)
                order.save() 

                # Create order-specific payment methods
                for payment_method in payment_methods:
                    data = {
                        "order": order.id,
                        "payment_method": payment_method.id,
                        "payment_type": payment_method.payment_type.id
                    }
                    order_method = serializers.OrderPaymentSerializer(data=data)
                    if order_method.is_valid():
                        order_payment_methods.append(order_method.save())
                order_payment_methods = serializers.OrderPaymentSerializer(order_payment_methods, many=True)
            else:
                order_methods = models.OrderPayment.objects.filter(order__id=order.id)
                if order_methods.exists():
                    order_payment_methods = serializers.OrderPaymentSerializer(order_methods, many=True)
            
            response["order_payment_methods"] = order_payment_methods.data

            context = { 'wallet_hash': wallet_hash }
            serialized_order = serializers.OrderSerializer(order, context=context)
            response["order"] = serialized_order.data
            
            # Create PAID_PENDING status for order
            serialized_status = serializers.StatusSerializer(data={'status': StatusType.PAID_PENDING, 'order': pk})
            if not serialized_status.is_valid():            
                raise ValidationError(serialized_status.errors)
            
            send_push_notification([order.get_seller().wallet_hash], f"Order #{order.id} payment pending confirmation", extra={'order_id': order.id})
            
            serialized_status = serializers.StatusReadSerializer(serialized_status.save())
            websocket.send_order_update({'success' : True, 'status': serialized_status.data}, pk)
            response["status"] = serialized_status.data
            return Response(response, status=status.HTTP_200_OK)

        except (ValidationError, models.Order.DoesNotExist) as err:
            return Response({'error': err.args[0]}, status=status.HTTP_400_BAD_REQUEST)
    
    @action(detail=True, methods=['post'])
    def seller_confirm_payment(self, request, pk):
        wallet_hash = request.user.wallet_hash
        try:
            order = models.Order.objects.get(pk=pk)
            
            # Require that user is seller
            seller = None
            if order.ad_snapshot.trade_type == models.TradeType.SELL:
                seller = order.ad_snapshot.ad.owner
            else:
                seller = order.owner
            if wallet_hash != seller.wallet_hash:
                raise ValidationError('Caller must be seller')
            
            validate_status_inst_count(StatusType.PAID, pk)
            validate_status_progression(StatusType.PAID, pk)

            # Create PAID status for order
            serialized_status = serializers.StatusSerializer(data={
                'status': StatusType.PAID, 
                'order': pk,
                'created_by': wallet_hash
            })
            if not serialized_status.is_valid():
                raise ValidationError(serialized_status.errors)
            serialized_status = serializers.StatusReadSerializer(serialized_status.save())

            # Create RELEASE transaction record for order contract
            contract = models.Contract.objects.get(order__id=pk)
            _, _ = models.Transaction.objects.get_or_create(contract=contract, action=models.Transaction.ActionType.RELEASE)

            # Send push notif and WebSocket update
            send_push_notification([order.get_buyer().wallet_hash], f"Order #{order.id} payment confirmed", extra={'order_id': order.id})
            websocket.send_order_update({'success' : True, 'status': serialized_status.data}, pk)
            return Response(serialized_status.data, status=status.HTTP_200_OK)

        except (ValidationError, models.Order.DoesNotExist) as err:
            return Response({'error': err.args[0]}, status=status.HTTP_400_BAD_REQUEST)
    
    def _check_status_edit_permissions(self, order, wallet_hash):
        '''Throws an error if wallet_hash is not a participant of status's order'''
        
        members = order.get_members()
        if wallet_hash == members['seller'].peer.wallet_hash:
            return members['seller']
        if wallet_hash == members['buyer'].peer.wallet_hash:
            return members['buyer']
        raise ValidationError('User not allowed to perform this action')
    