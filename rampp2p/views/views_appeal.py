from rest_framework import status, viewsets
from rest_framework.response import Response
from rest_framework.decorators import action

from django.db import transaction
from django.core.exceptions import ValidationError

from authentication.token import TokenAuthentication
from authentication.permissions import RampP2PIsAuthenticated

import rampp2p.models as models
import rampp2p.serializers as serializers
import rampp2p.utils.websocket as websocket

from rampp2p.validators import *
from rampp2p.utils.fees import get_trading_fees
from rampp2p.utils.handler import update_order_status
from rampp2p.utils.notifications import send_push_notification
from rampp2p.viewcodes import WSGeneralMessageType

import math

class AppealViewSet(viewsets.GenericViewSet):
    authentication_classes = [TokenAuthentication]
    permission_classes = [RampP2PIsAuthenticated]
    serializer_class = serializers.AppealSerializer
    queryset = models.Appeal.objects.all()

    def list(self, request):
        wallet_hash = request.user.wallet_hash
        try:
            arbiter = models.Arbiter.objects.get(wallet_hash=wallet_hash)
            appeal_state = request.query_params.get('state')
            limit = int(request.query_params.get('limit', 0))
            page = int(request.query_params.get('page', 1))

            if limit < 0:
                return Response({'error': 'limit must be a non-negative number'}, status=status.HTTP_400_BAD_REQUEST)
            
            if page < 1:
                return Response({'error': 'invalid page number'}, status=status.HTTP_400_BAD_REQUEST)
            
            arbiter_order_ids = list(models.Order.objects.filter(arbiter__wallet_hash=arbiter.wallet_hash).values_list('id', flat=True))
            queryset = models.Appeal.objects.filter(order__pk__in=arbiter_order_ids).order_by('created_at')

            if appeal_state == 'PENDING':
                queryset = queryset.exclude(resolved_at__isnull=False)
            if appeal_state == 'RESOLVED':
                queryset = queryset.exclude(resolved_at__isnull=True)

            # Count total pages
            count = queryset.count()
            total_pages = page
            if limit > 0:
                total_pages = math.ceil(count / limit)

            # Splice queryset
            offset = (page - 1) * limit
            page_results = queryset[offset:offset + limit]

            context = { 'wallet_hash': wallet_hash }
            serializer = serializers.AppealSerializer(page_results, context=context, many=True)
            
            # get this user's unread orders
            member_orders = models.OrderMember.objects.filter(
                Q(read_at__isnull=True) & 
                (Q(peer__wallet_hash=wallet_hash) | Q(arbiter__wallet_hash=wallet_hash))).values_list('order', flat=True)
            
            # count which appeals have orders that are subset of this user's unread orders
            unread_count = models.Appeal.objects.filter(order__in=member_orders).count()
            
            data = {
                'appeals': serializer.data,
                'count': count,
                'total_pages': total_pages,
                'unread_count': unread_count
            }
            return Response(data, status.HTTP_200_OK)
        except Exception as err:
            return Response({'error': err.args[0]}, status=status.HTTP_400_BAD_REQUEST)
    
    def retrieve(self, request, pk):
        wallet_hash = request.user.wallet_hash
        try:
            appeal = models.Appeal.objects.get(pk=pk)
            self._check_appeal_permissions(wallet_hash, appeal.order)
            response = self._retrieve(request, appeal)
            return Response(response, status=status.HTTP_200_OK)
        except (ValidationError, models.Appeal.DoesNotExist) as err:
            return Response({'error': err.args[0]}, status=status.HTTP_400_BAD_REQUEST)

    @action(detail=True, methods=['get'])
    def retrieve_by_order(self, request, pk):
        wallet_hash = request.user.wallet_hash
        try:
            appeal = models.Appeal.objects.get(order__id=pk)
            self._check_appeal_permissions(wallet_hash, appeal.order)
            response = self._retrieve(request, appeal)
            return Response(response, status=status.HTTP_200_OK)
        except (ValidationError, models.Appeal.DoesNotExist) as err:
            return Response({'error': err.args[0]}, status=status.HTTP_400_BAD_REQUEST)
        
    def create(self, request):
        '''
        Submits an appeal for an order.
        Requirements:
            (1) The creator of appeal must be the buyer/seller.
            (2) The order must be expired.
            (3) The latest order status must be one of ['ESCRW', 'PD_PN', 'PD']
        Restrictions:
            (1) The seller cannot appeal once they marked the order as 'PD'
            (2) The seller/buyer cannot appeal once the order is completed (i.e. 'RLS' or 'RFN')
            (3) The seller/buyer cannot appeal before the funds are escrowed (i.e. status = 'SBM', 'CNF', 'ESCRW_PN')
        '''
        wallet_hash = request.user.wallet_hash
        order_id = request.data.get('order_id')
        try:
            order = models.Order.objects.get(id=order_id)
            if not order.is_cash_in:
                appealable, appealable_at = order.is_appealable()
                if not appealable:
                    response_data = {
                        'error': 'order is not appealable now',
                        'appealable_at': appealable_at
                    }
                    return Response(response_data, status=status.HTTP_400_BAD_REQUEST)
            
            self._check_appeal_permissions(wallet_hash, order)
            validate_status_inst_count(StatusType.APPEALED, order_id)
            validate_status_progression(StatusType.APPEALED, order_id)
            appeal_type = request.data.get('type')
            models.AppealType(appeal_type)

            peer = models.Peer.objects.get(wallet_hash=wallet_hash)
            data = {
                'order': order_id,
                'owner': peer.id,
                'type': appeal_type,
                'reasons': request.data.get('reasons')
            }

            with transaction.atomic():
                serialized_appeal = serializers.AppealCreateSerializer(data=data)
                if not serialized_appeal.is_valid():
                    raise ValidationError(serialized_appeal.errors)
                
                appeal = serialized_appeal.save()
                serialized_status = serializers.StatusSerializer(data={
                    'status': StatusType.APPEALED,
                    'order': order_id,
                    'created_by': wallet_hash
                })

                if not serialized_status.is_valid():
                    raise ValidationError(serialized_status.errors)
                
                serialized_appeal = serializers.AppealSerializer(appeal)
                serialized_status = serializers.StatusReadSerializer(serialized_status.save())
                response_data = {
                    'appeal': serialized_appeal.data,
                    'status': serialized_status.data
                }
                
                # Send WebSocket updates
                websocket.send_order_update({'success' : True, 'status': serialized_status.data}, order_id)

                # Serialize appeal for arbiter
                rbtr_wallet_hash = appeal.order.arbiter.wallet_hash
                rbtr_appeal = serializers.AppealSerializer(appeal, context={'wallet_hash': rbtr_wallet_hash})
                
                # Count the number of unread appeals for arbiter
                rbtr_unread_orders = models.OrderMember.objects.filter(Q(read_at__isnull=True) & Q(arbiter__wallet_hash=appeal.order.arbiter.wallet_hash)).values_list('order', flat=True)
                rbtr_unread_apls_count = models.Appeal.objects.filter(order__in=rbtr_unread_orders).count()
                
                # Send appeal WebSocket notification to arbiter
                websocket.send_general_update({
                    'type': WSGeneralMessageType.NEW_APPEAL.value,
                    'extra': {
                        'appeal': rbtr_appeal.data,
                        'unread_count': rbtr_unread_apls_count
                    }
                }, rbtr_wallet_hash)

                # Send push notifications
                party_a = appeal.order.ad_snapshot.ad.owner.wallet_hash
                party_b = appeal.order.owner.wallet_hash
                arbiter = appeal.order.arbiter.wallet_hash
                recipients = [arbiter]
                if wallet_hash == party_a:
                    recipients.append(party_b)
                if wallet_hash == party_b:
                    recipients.append(party_a)
                message = f'Order #{order_id} {appeal_type} appealed'
                send_push_notification(recipients, message, extra={ 'order_id': order_id, 'appeal_id':  appeal.id})

                return Response(response_data, status=status.HTTP_200_OK)
        except Exception as err:
            return Response({'error': err.args[0]}, status=status.HTTP_400_BAD_REQUEST)

    @action(detail=True, methods=['post'])
    def pending_release(self, request, pk):
        '''
        Updates the order status to RELEASE_PENDING marking an appealed order for release transaction.
        Requires: (1) caller must be the order's arbiter; (2) appeal must be existing
        '''
        try:
            wallet_hash = request.user.wallet_hash
            appeal = models.Appeal.objects.get(pk=pk)
            
            # User must be order's arbiter
            if wallet_hash != appeal.order.arbiter.wallet_hash:
                raise ValidationError(f'User not allow to perform this action')
            
            # Status validations
            status_type = StatusType.RELEASE_PENDING
            validate_status_inst_count(status_type, appeal.order.id)
            validate_exclusive_stats(status_type, appeal.order.id)
            validate_status_progression(status_type, appeal.order.id)                        

            with transaction.atomic():
                # Update status to RELEASE_PENDING
                serialized_status = update_order_status(appeal.order.id, status_type, wallet_hash=wallet_hash)

                contract = models.Contract.objects.get(order__id=appeal.order.id)
                _, _ = models.Transaction.objects.get_or_create(
                    contract=contract,
                    action=models.Transaction.ActionType.RELEASE,
                )
            
            # Notify order update subscribers
            websocket_msg = { 'success' : True, 'status': serialized_status.data }
            websocket.send_order_update(websocket_msg, pk)

            return Response(serialized_status.data, status=status.HTTP_200_OK)
        except (ValidationError, models.Appeal.DoesNotExist, models.Contract.DoesNotExist) as err:
            return Response({"success": False, "error": err.args[0]}, status=status.HTTP_400_BAD_REQUEST)

    @action(detail=True, methods=['post'])
    def pending_refund(self, request, pk):
        '''
        Updates the order status to REFUND_PENDING marking an appealed order as awaiting for refund transaction.
        Requirements: (1) Caller must be the order's arbiter, (2) appeal must be existing
        '''
        try:
            wallet_hash = request.user.wallet_hash
            appeal = models.Appeal.objects.get(pk=pk)

            # User must be order's arbiter
            if wallet_hash != appeal.order.arbiter.wallet_hash:
                raise ValidationError(f'User not allow to perform this action')
        
            # Status validations
            status_type = StatusType.REFUND_PENDING
            validate_status_inst_count(status_type, appeal.order.id)
            validate_exclusive_stats(status_type, appeal.order.id)
            validate_status_progression(status_type, appeal.order.id)

            with transaction.atomic():
                # Update status to REFUND_PENDING
                serialized_status = update_order_status(appeal.order.id, status_type, wallet_hash=wallet_hash)

                contract = models.Contract.objects.get(order__id=appeal.order.id)
                _, _ = models.Transaction.objects.get_or_create(
                    contract=contract,
                    action=models.Transaction.ActionType.REFUND,
                )
                
                
            # notify order update subscribers
            websocket_msg = {
                'success' : True,
                'status': serialized_status.data
            }
            websocket.send_order_update(websocket_msg, pk)
            
            return Response(serialized_status.data, status=status.HTTP_200_OK)    
        except (ValidationError, models.Appeal.DoesNotExist, models.Contract.DoesNotExist) as err:
            return Response({"success": False, "error": err.args[0]}, status=status.HTTP_400_BAD_REQUEST)

    def _retrieve(self, request, appeal: models.Appeal):
        wallet_hash = request.user.wallet_hash
        serialized_appeal = None            

        context = { 'wallet_hash': wallet_hash }
        serialized_appeal = serializers.AppealSerializer(appeal, context=context)
        response = {
            'appeal': serialized_appeal if serialized_appeal is None else serialized_appeal.data,
        }
        return response
        
    def _check_appeal_permissions(self, wallet_hash, order):
        '''Throws an error if user is not associated to the appeal (not buyer, seller, nor arbiter).'''
        
        if (wallet_hash != order.owner.wallet_hash and
            wallet_hash != order.ad_snapshot.ad.owner.wallet_hash and
            wallet_hash != order.arbiter.wallet_hash):
            raise ValidationError('User not allowed to perform this action')
