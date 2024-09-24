from rest_framework import status, viewsets
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.decorators import action

from django.http import Http404
from django.utils import timezone
from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.db.models import Q, OuterRef, Subquery, Case, When, Value, BooleanField

from datetime import datetime, time, timedelta
from typing import List
from decimal import Decimal, ROUND_HALF_UP
import math

from authentication.token import TokenAuthentication
from authentication.permissions import RampP2PIsAuthenticated

import rampp2p.models as models
import rampp2p.serializers as serializers
import rampp2p.utils.utils as utils
import rampp2p.utils.websocket as websocket

from rampp2p.utils.notifications import send_push_notification
from rampp2p.viewcodes import WSGeneralMessageType
from rampp2p.validators import *

import logging
logger = logging.getLogger(__name__)

class CashinOrderView(APIView):

    def get(self, request):
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
        params = self._parse_params(request=request)

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
            is_cash_in = request.data.get('is_cash_in', False)
            crypto_amount = request.data.get('crypto_amount')
            if crypto_amount is None or crypto_amount == 0:
                raise ValidationError('crypto_amount field is required')

            ad = models.Ad.objects.get(pk=request.data.get('ad'))
            owner = models.Peer.objects.get(wallet_hash=wallet_hash)
            payment_method_ids = request.data.get('payment_methods', [])
            crypto_amount = Decimal(crypto_amount)

            # require payment methods if creating a SELL order
            if ad.trade_type == models.TradeType.BUY:
                if len(payment_method_ids) == 0:
                    raise ValidationError('payment_methods field is required for SELL orders')            
                self._check_payment_permissions(wallet_hash, payment_method_ids)
            
            # check permissions
            self._check_create_permissions(wallet_hash, ad.id)

            # query market price for ad fiat currency
            market_price = models.MarketRate.objects.filter(currency=ad.fiat_currency.symbol)
            if market_price.exists():
                market_price = market_price.first()
            else:
                raise ValidationError(f'market price for currency {ad.fiat_currency.symbol} does not exist.')
            
        except (models.Ad.DoesNotExist, models.Peer.DoesNotExist, ValidationError) as err:
            return Response({'error': err.args[0]}, status=status.HTTP_400_BAD_REQUEST)

        try:
            with transaction.atomic():
                # Create a snapshot of ad
                ad_snapshot = models.AdSnapshot(
                    ad = ad,
                    trade_type = ad.trade_type,
                    price_type = ad.price_type,
                    fiat_currency = ad.fiat_currency,
                    crypto_currency = ad.crypto_currency,
                    fixed_price = ad.fixed_price,
                    floating_price = ad.floating_price,
                    market_price = market_price.price,
                    trade_floor = ad.trade_floor,
                    trade_ceiling = ad.trade_ceiling,
                    trade_amount = ad.trade_amount,
                    appeal_cooldown_choice = ad.appeal_cooldown_choice,
                    trade_amount_in_fiat = ad.trade_amount_in_fiat,
                    trade_limits_in_fiat = ad.trade_limits_in_fiat
                )
                ad_snapshot.save()
                ad_payment_methods = ad.payment_methods.all()
                ad_payment_types = [pm.payment_type for pm in ad_payment_methods]
                ad_snapshot.payment_types.set(ad_payment_types)

                # Generate order tracking id
                tracking_id = self._generate_tracking_id()

                # Create the order data
                data = {
                    'owner': owner.id,
                    'ad_snapshot': ad_snapshot.id,
                    'payment_methods': payment_method_ids,
                    'crypto_amount': crypto_amount,
                    'is_cash_in': is_cash_in,
                    'tracking_id': tracking_id
                }
                # Calculate the locked ad price
                price = None
                if ad_snapshot.price_type == models.PriceType.FLOATING:
                    market_price = market_price.price
                    price = market_price * (ad_snapshot.floating_price/100)
                else:
                    price = ad_snapshot.fixed_price
                data['locked_price'] = Decimal(price).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
                serialized_order = serializers.WriteOrderSerializer(data=data)

                # Raise error if order isn't valid
                serialized_order.is_valid(raise_exception=True)
                order = serialized_order.save()
                
                # Set order expiration date
                expiration = order.created_at + timedelta(hours=24)
                if is_cash_in:
                    expiration = order.created_at + timedelta(minutes=15)
                order.expires_at = expiration

                # Create SUBMITTED status for order
                submitted_status = serializers.StatusSerializer(data={'status': StatusType.SUBMITTED, 'order': order.id})
                submitted_status.is_valid(raise_exception=True)
                submitted_status = serializers.StatusSerializer(submitted_status.save()).data
                
                # Create and associate order members
                seller, buyer = None, None
                if ad_snapshot.trade_type == models.TradeType.SELL:
                    seller = ad_snapshot.ad.owner
                    buyer = order.owner
                else:
                    seller = order.owner
                    buyer = ad_snapshot.ad.owner
                seller_member = models.OrderMember.objects.create(order=order, peer=seller, type=models.OrderMember.MemberType.SELLER)
                buyer_member = models.OrderMember.objects.create(order=order, peer=buyer, type=models.OrderMember.MemberType.BUYER)
                
                # Mark order creator member as already read
                if seller_member.peer.wallet_hash == order.owner.wallet_hash:
                    seller_member.read_at = timezone.now()
                    seller_member.save()
                if buyer_member.peer.wallet_hash == order.owner.wallet_hash:
                    buyer_member.read_at = timezone.now()
                    buyer_member.save()

                order.save()

                # If order is cash-in, create OrderPayment records
                if order.is_cash_in:
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

                # Serialize response data
                serialized_order = serializers.OrderSerializer(order, context={'wallet_hash': wallet_hash}).data    
                response = {
                    'success': True,
                    'order': serialized_order,
                    'status': submitted_status
                }
        except Exception as err:
            return Response({'error': err.args[0]}, status=status.HTTP_400_BAD_REQUEST)
        
        # Send push notification to the Ad owner
        extra = {'order_id': serialized_order['id']}
        send_push_notification([ad.owner.wallet_hash], "Received a new order", extra=extra)

        # Recount the number of unopened orders for the Ad owner, send this value to general websocket
        unread_count = models.OrderMember.objects.filter(Q(read_at__isnull=True) & Q(peer__wallet_hash=ad.owner.wallet_hash)).count()
        serialized_order = serializers.OrderSerializer(order, context={'wallet_hash': ad.owner.wallet_hash})
        websocket.send_general_update({
            'type': WSGeneralMessageType.NEW_ORDER.value,
            'extra': {
                'order': serialized_order.data,
                'unread_count': unread_count
            }
        }, ad.owner.wallet_hash)

        return Response(response, status=status.HTTP_201_CREATED)

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

    @action(detail=True, methods=['get'])
    def list_status(self, request, pk):
        queryset = Status.objects.filter(order__id=pk)
        serializer = serializers.StatusSerializer(queryset, many=True)
        return Response(serializer.data, status=status.HTTP_200_OK)

    @action(detail=True, methods=['patch'])
    def read_status(self, request, pk):
        try:
            # check edit permission
            member = self._check_status_edit_permissions(pk, request.user.wallet_hash)
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
        except ValidationError as err:
            return Response({'error': err.args[0]}, status=status.HTTP_400_BAD_REQUEST)
    
    @action(detail=True, methods=['post'])
    def confirm(self, request, pk):
        '''Confirms an order. Is callable only by the ad owner.'''

        wallet_hash = request.user.wallet_hash
        try:
            with transaction.atomic():
                order = models.Order.objects.get(pk=pk)
                
                # User must be ad owner
                is_ad_owner = models.Ad.objects.filter(Q(owner__wallet_hash=wallet_hash) & Q(pk=order.ad_snapshot.ad.id)).exists()
                if not is_ad_owner:
                    raise ValidationError('User must be ad owner')
                    
                validate_status(pk, StatusType.SUBMITTED)
                validate_status_inst_count(StatusType.CONFIRMED, pk)
                validate_status_progression(StatusType.CONFIRMED, pk)

                order = models.Order.objects.get(pk=pk)

                if order.expires_at and order.expires_at < timezone.now():
                    raise ValidationError('Cannot confirm expired order')
                
                order.expires_at = None
                order.save()

                # Decrease the Ad's trade amount
                # If ad snapshot's trade amount is in fiat, convert order crypto_amount
                # to fiat and decrement this from ad's current trade_amount
                amount_to_dec = order.crypto_amount
                if (order.ad_snapshot.ad.trade_amount_in_fiat):
                    # convert to fiat
                    amount_to_dec = order.crypto_amount * order.locked_price

                trade_amount = order.ad_snapshot.ad.trade_amount - amount_to_dec
                if trade_amount < 0:
                    raise ValidationError('crypto_amount exceeds ad remaining trade_amount')
                ad = models.Ad.objects.get(pk=order.ad_snapshot.ad.id)
                ad.trade_amount = trade_amount
                ad.save()

        except (ValidationError, IntegrityError, models.Order.DoesNotExist, models.Ad.DoesNotExist) as err:
            return Response({'error': err.args[0]}, status=status.HTTP_400_BAD_REQUEST)
                
        serialized_status = serializers.StatusSerializer(data={
            'status': StatusType.CONFIRMED,
            'order': pk
        })

        if not serialized_status.is_valid():
            return Response(serialized_status.errors, status=status.HTTP_400_BAD_REQUEST)
        
        serialized_status = serializers.StatusReadSerializer(serialized_status.save())
        
        # send websocket notification
        websocket.send_order_update({
            'success': True,
            'status': serialized_status.data
        }, pk)
        
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
                # Update Ad trade_amount if order was CONFIRMED
                order = models.Order.objects.get(pk=pk)
                current_status = utils.get_last_status(order.id)
                if current_status.status == StatusType.CONFIRMED:
                    trade_amount = order.ad_snapshot.ad.trade_amount + order.crypto_amount        
                    ad = models.Ad.objects.get(pk=order.ad_snapshot.ad.id)
                    ad.trade_amount = trade_amount
                    ad.save()
                    
                # Create CANCELED status for order
                serializer = serializers.StatusSerializer(data={'status': StatusType.CANCELED, 'order': pk})
                if not serializer.is_valid():
                    raise ValidationError(serializer.errors)
                serialized_status = serializers.StatusReadSerializer(serializer.save())

                # Mark order as read by all parties
                members = order.members.all()
                for member in members:
                    member.read_at = timezone.now()
                    member.save()

                # Send WebSocket update
                websocket_msg = {'success' : True, 'status': serialized_status.data}
                websocket.send_order_update(websocket_msg, pk)

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
            status_serializer = serializers.StatusSerializer(data={'status': StatusType.ESCROW_PENDING, 'order': pk})
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
                order_payment_methods = []
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
                response["order_payment_methods"] = order_payment_methods.data

            context = { 'wallet_hash': wallet_hash }
            serialized_order = serializers.OrderSerializer(order, context=context)
            response["order"] = serialized_order.data
            
            # Create PAID_PENDING status for order
            serialized_status = serializers.StatusSerializer(data={
                'status': StatusType.PAID_PENDING,
                'order': pk
            })

            if not serialized_status.is_valid():            
                raise ValidationError(serialized_status.errors)
            
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
            serialized_status = serializers.StatusSerializer(data={'status': StatusType.PAID, 'order': pk})
            if not serialized_status.is_valid():
                raise ValidationError(serialized_status.errors)
            serialized_status = serializers.StatusReadSerializer(serialized_status.save())

            # Create RELEASE transaction record for order contract
            contract = models.Contract.objects.get(order__id=pk)
            _, _ = models.Transaction.objects.get_or_create(contract=contract, action=models.Transaction.ActionType.RELEASE)

            # Send WebSocket update
            websocket.send_order_update({'success' : True, 'status': serialized_status.data}, pk)
            return Response(serialized_status.data, status=status.HTTP_200_OK)

        except (ValidationError, models.Order.DoesNotExist) as err:
            return Response({'error': err.args[0]}, status=status.HTTP_400_BAD_REQUEST)
    
    def _parse_params(self, request):
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
    
    def _generate_tracking_id(self):
        ''' PEO[year][month][day]-[order_count_today] e.g. PEO20211201-0001 '''
        today = datetime.today()
        today_midnight = datetime.combine(today, time.min)
        next_day_midnight = datetime.combine(today + timedelta(days=1), time.min)
        order_count = models.Order.objects.filter(created_at__gte=today_midnight, created_at__lt=next_day_midnight).count()
        tracking_id = f'PEO{today.year}{str(today.month).zfill(2)}{str(today.day).zfill(2)}-{str(order_count).zfill(4)}'
        return tracking_id
    
    def _check_create_permissions(self, wallet_hash, pk):
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

    def _check_payment_permissions(self, wallet_hash, payment_method_ids: List[int]):
        ''' Validates if peer owns the payment methods '''
        owned_payment_methods = models.PaymentMethod.objects.filter(Q(owner__wallet_hash=wallet_hash) & Q(id__in=payment_method_ids))
        if len(payment_method_ids) != owned_payment_methods.count():
            raise ValidationError(f'Invalid payment method(s). Expected {len(payment_method_ids)} owned payment methods, got {owned_payment_methods.count()}.')
    
    def _check_status_edit_permissions(self, order_pk, wallet_hash):
        '''Throws an error if wallet_hash is not a participant of status's order'''
        
        members = utils.get_order_members(order_pk)
        if wallet_hash == members['seller'].peer.wallet_hash:
            return members['seller']
        if wallet_hash == members['buyer'].peer.wallet_hash:
            return members['buyer']
        raise ValidationError('User not allowed to perform this action')
        
class OrderStatusViewSet(viewsets.GenericViewSet):
    authentication_classes = [TokenAuthentication]
    permission_classes = [RampP2PIsAuthenticated]
    queryset = models.Status.objects.all()
    
   