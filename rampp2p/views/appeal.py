from rest_framework.views import APIView
from rest_framework import status
from rest_framework.response import Response
from django.core.exceptions import ValidationError

from rampp2p.models import (
    TradeType,
    StatusType,
    Peer,
    Order,
    Contract,
    Transaction,
    AppealType
)

from rampp2p.serializers import (
    StatusSerializer,
    AppealSerializer,
    AppealCreateSerializer,
    TransactionSerializer
)
from rampp2p.viewcodes import ViewCode
from rampp2p.validators import *
from rampp2p.utils.signature import verify_signature, get_verification_headers
from rampp2p.utils.transaction import validate_transaction
from rampp2p.utils.utils import is_order_expired
from rampp2p.utils.handler import update_order_status

import logging
logger = logging.getLogger(__name__)
    
class AppealRequest(APIView):
    '''
    Submits an appeal for an order.
    Requirements:
        (1) The creator of appeal must be the buyer/seller.
        (2) The order must be expired.
        (3) The latest order status must be one of ['ESCRW', 'PD_PN', 'PD']
    Restrictions:
        (1) The seller cannot appeal once they marked the order as 'PD'
        (2) The seller/buyer cannot appeal once the order is completed (i.e. 'RLS', 'CNCL' or 'RFN')
        (3) The seller/buyer cannot appeal before the funds are escrowed (i.e. status = 'SBM', 'CNF', 'ESCRW_PN')
    '''
    def post(self, request, pk):
        try:
            # validate signature
            signature, timestamp, wallet_hash = get_verification_headers(request)
            message = ViewCode.APPEAL_REQUEST.value + '::' + timestamp
            verify_signature(wallet_hash, signature, message)

            # validate permissions
            self.validate_permissions(wallet_hash, pk)
        except ValidationError as err:
            return Response({'error': err.args[0]}, status=status.HTTP_403_FORBIDDEN)
        
        try:
            # if not is_order_expired(pk):
            #     raise ValidationError('order is not expired')
            validate_status_inst_count(StatusType.APPEALED, pk)
            validate_status_progression(StatusType.APPEALED, pk)
            appeal_type = request.data.get('type')
            AppealType(appeal_type)
        except (ValidationError, ValueError) as err:
            return Response({'error': err.args[0]}, status=status.HTTP_400_BAD_REQUEST)

        # create and Appeal record
        peer = Peer.objects.get(wallet_hash=wallet_hash)
        data = {
            'order': pk,
            'owner': peer.id,
            'type': appeal_type,
            'reasons': request.data.get('reasons')
        }
        logger.warn(f'data;{data}')
        serialized_appeal = AppealCreateSerializer(data=data)
        if not serialized_appeal.is_valid():
            return Response({'error': serialized_appeal.errors}, status=status.HTTP_400_BAD_REQUEST)        
        serialized_appeal = AppealSerializer(serialized_appeal.save())

        # create APPEALED status for order
        serialized_status = StatusSerializer(data={
            'status': StatusType.APPEALED,
            'order': pk
        })
        if not serialized_status.is_valid():
            return Response(serialized_status.errors, status=status.HTTP_400_BAD_REQUEST)
        serialized_status = StatusSerializer(serialized_status.save())

        response_data = {
            'appeal': serialized_appeal.data,
            'status': serialized_status.data
        }
        return Response(response_data, status=status.HTTP_200_OK)        
    
    def validate_permissions(self, wallet_hash, pk):
        '''
        AppealRelease is callable only by the buyer/seller.
        '''

        try:
            order = Order.objects.get(pk=pk)
            caller = Peer.objects.get(wallet_hash=wallet_hash)
        except (Order.DoesNotExist, Peer.DoesNotExist) as err:
            raise ValidationError(err.args[0])
        
        if (caller.wallet_hash != order.owner.wallet_hash and
            caller.wallet_hash != order.ad.owner.wallet_hash):
            raise ValidationError('caller not affiliated to this order')
        

class AppealPendingRelease(APIView):
    '''
    Marks an appealed order for release of escrowed funds, updating the order status to RELEASE_PENDING.
    The order status is automatically updated to RELEASED when the contract address receives an 
    outgoing transaction that matches the requisites of the contract.
    Note: This endpoint must be invoked before the actual transfer of funds.

    Requirements:
        (1) Caller must be the order's arbiter
        (2) Order must have an existing appeal
    '''
    def post(self, request, pk):

        try:
            # Validate signature
            signature, timestamp, wallet_hash = get_verification_headers(request)
            message = ViewCode.APPEAL_PENDING_RELEASE.value + '::' + timestamp
            verify_signature(wallet_hash, signature, message)

            # Validate permissions
            self.validate_permissions(wallet_hash, pk)
        except ValidationError as err:
            return Response({"success": False, "error": err.args[0]}, status=status.HTTP_403_FORBIDDEN)

        try:
            # Status validations
            status_type = StatusType.RELEASE_PENDING
            validate_status_inst_count(status_type, pk)
            validate_exclusive_stats(status_type, pk)
            validate_status_progression(status_type, pk)                        

            # Update status to RELEASE_PENDING
            update_order_status(pk, status_type)
            
        except ValidationError as err:
            return Response({"success": False, "error": err.args[0]}, status=status.HTTP_400_BAD_REQUEST)
  
        return Response(status=status.HTTP_200_OK)
    
    def validate_permissions(self, wallet_hash, pk):
        '''
        validate_permissions will raise a ValidationError if:
            (1) caller is not order's arbiter,
            (2) order's current status is not RELEASE_APPEALED or REFUND_APPEALED
        '''
        prefix = "ValidationError:"

        try:
            caller = Peer.objects.get(wallet_hash=wallet_hash)
            order = Order.objects.get(pk=pk)
            curr_status = Status.objects.filter(order=order).latest('created_at')
        except (Peer.DoesNotExist, Order.DoesNotExist) as err:
            raise ValidationError(f'{prefix} {err.args[0]}')
        
        # Raise error if caller is not order's arbiter
        if caller.wallet_hash != order.arbiter.wallet_hash:
            raise ValidationError(f'{prefix} Caller must be order arbiter.')
        
        # Raise error if order's current status is not RELEASE_APPEALED nor REFUND_APPEALED
        if (curr_status.status != StatusType.RELEASE_APPEALED and 
            curr_status.status != StatusType.REFUND_APPEALED):
                raise ValidationError(f'{prefix} No existing release/refund appeal for order #{pk}.')

class AppealPendingRefund(APIView):
    '''
    Marks an appealed order for refund of escrowed funds, updating the order status to REFUND_PENDING.
    The order status is automatically updated to REFUNDED when the contract address receives an 
    outgoing transaction that matches the requisites of the contract.
    Note: This endpoint must be invoked before the actual transfer of funds.

    Requirements:
        (1) Caller must be the order's arbiter
        (2) Order must have an existing appeal
    '''
    def post(self, request, pk):
        
        try:
            # Validate signature
            signature, timestamp, wallet_hash = get_verification_headers(request)
            message = ViewCode.APPEAL_PENDING_REFUND.value + '::' + timestamp
            verify_signature(wallet_hash, signature, message)

            # Validate permissions
            self.validate_permissions(wallet_hash, pk)
        
            # Status validations
            status_type = StatusType.REFUND_PENDING
            validate_status_inst_count(status_type, pk)
            validate_exclusive_stats(status_type, pk)
            validate_status_progression(status_type, pk)

            # Update status to REFUND_PENDING
            update_order_status(pk, status_type)
            
        except ValidationError as err:
            return Response({"success": False, "error": err.args[0]}, status=status.HTTP_400_BAD_REQUEST)
        
        return Response(status=status.HTTP_200_OK)
    
    def validate_permissions(self, wallet_hash, pk):
        '''
        validate_permissions will raise a ValidationError if:
            (1) caller is not order's arbiter,
            (2) order's current status is not RELEASE_APPEALED or REFUND_APPEALED
        '''
        prefix = "ValidationError:"

        try:
            caller = Peer.objects.get(wallet_hash=wallet_hash)
            order = Order.objects.get(pk=pk)
            curr_status = Status.objects.filter(order=order).latest('created_at')
        except (Peer.DoesNotExist, Order.DoesNotExist) as err:
            raise ValidationError(f'{prefix} {err.args[0]}')
        
        # Raise error if caller is not order's arbiter
        if caller.wallet_hash != order.arbiter.wallet_hash:
            raise ValidationError(f'{prefix} Caller must be order arbiter.')
        
        # Raise error if order's current status is not RELEASE_APPEALED nor REFUND_APPEALED
        if (curr_status.status != StatusType.RELEASE_APPEALED and 
            curr_status.status != StatusType.REFUND_APPEALED):
                raise ValidationError(f'{prefix} No existing release/refund appeal for order #{pk}.')

class VerifyRelease(APIView):
    '''
    Manually marks the order as (status) RELEASED by validating if a given transaction id (txid) 
    satisfies the prerequisites of its contract.
    Note: This endpoint should only be used as fallback for the ReleaseCrypto endpoint.

    Requirements:
        (1) Caller must be the order's arbiter or seller
        (2) The order's current status must be RELEASE_PENDING (created by calling ReleaseCrypto endpoint first)
        (3) TODO: An amount of time must already have passed since status RELEASE_PENDING was created
    '''
    def post(self, request, pk):

        try:
            # validate signature
            signature, timestamp, wallet_hash = get_verification_headers(request)
            message = ViewCode.ORDER_RELEASE.value + '::' + timestamp
            verify_signature(wallet_hash, signature, message)

            # validate permissions
            self.validate_permissions(wallet_hash, pk)
        except ValidationError as err:
            return Response({"success": False, "error": err.args[0]}, status=status.HTTP_403_FORBIDDEN)

        try:
            # status validations
            status_type = StatusType.RELEASED
            validate_status_inst_count(status_type, pk)
            validate_exclusive_stats(status_type, pk)
            validate_status_progression(status_type, pk)            
            
            txid = request.data.get('txid')
            if txid is None:
                raise ValidationError('txid field is required')

            contract = Contract.objects.get(order__id=pk)
            transaction, _ = Transaction.objects.get_or_create(
                contract=contract,
                action=Transaction.ActionType.RELEASE,
                txid=txid
            )

            result = {
                'txid': txid,
                'transaction': TransactionSerializer(transaction).data
            }

            # Validate the transaction
            validate_transaction(
                txid=transaction.txid,
                action=Transaction.ActionType.RELEASE,
                contract_id=contract.id
            )
            
        except (ValidationError, Contract.DoesNotExist) as err:
            return Response({"success": False, "error": err.args[0]}, status=status.HTTP_400_BAD_REQUEST)
  
        return Response(result, status=status.HTTP_200_OK)
    
    def validate_permissions(self, wallet_hash, pk):
        '''
        validate_permissions will raise a ValidationError if:
            (1) caller is not the order's arbiter nor seller
            (2) the order's current status is not RELEASE_PENDING nor PAID
        '''
        prefix = "ValidationError:"

        try:
            caller = Peer.objects.get(wallet_hash=wallet_hash)
            order = Order.objects.get(pk=pk)
            curr_status = Status.objects.filter(order=order).latest('created_at')
        except (Peer.DoesNotExist, Order.DoesNotExist) as err:
            raise ValidationError(f'{prefix} {err.args[0]}')
        
        is_arbiter = False
        is_seller = False
        if caller.wallet_hash == order.arbiter.wallet_hash:
            is_arbiter = True
        elif order.ad.trade_type == TradeType.SELL:
            seller = order.ad.owner
            if caller.wallet_hash == seller.wallet_hash:
                is_seller = True

        if (not is_arbiter) and (not is_seller):
            raise ValidationError(f'{prefix} Caller must be seller or arbiter.')
        
        if not (curr_status.status == StatusType.RELEASE_PENDING or curr_status.status == StatusType.PAID):
            raise ValidationError(f'{prefix} Current status of order #{pk} must be {StatusType.RELEASE_PENDING.label} or {StatusType.PAID.label}.')

class VerifyRefund(APIView):
    '''
    Manually marks the order as (status) REFUNDED by validating if a given transaction id (txid) 
    satisfies the prerequisites of its contract.
    Note: This endpoint should only be used as fallback for the RefundCrypto endpoint.

    Requirements:
        (1) Caller must be the order's arbiter
        (2) The order's current status must be REFUND_PENDING (created by calling RefundCrypto endpoint first)
        (3) TODO: An amount of time must already have passed since status REFUND_PENDING was created
    '''
    def post(self, request, pk):

        try:
            # validate signature
            signature, timestamp, wallet_hash = get_verification_headers(request)
            message = ViewCode.ORDER_REFUND.value + '::' + timestamp
            verify_signature(wallet_hash, signature, message)

            # validate permissions
            self.validate_permissions(wallet_hash, pk)
        except ValidationError as err:
            return Response({"success": False, "error": err.args[0]}, status=status.HTTP_403_FORBIDDEN)

        try:
            # status validations
            status_type = StatusType.REFUNDED
            validate_status_inst_count(status_type, pk)
            validate_exclusive_stats(status_type, pk)
            validate_status_progression(status_type, pk)            
            
            txid = request.data.get('txid')
            if txid is None:
                raise ValidationError('txid field is required')

            contract = Contract.objects.get(order__id=pk)
            transaction, _ = Transaction.objects.get_or_create(
                contract=contract,
                action=Transaction.ActionType.REFUND,
                txid=txid
            )

            # Validate the transaction
            validate_transaction(
                txid=transaction.txid, 
                action=Transaction.ActionType.REFUND,
                contract_id=contract.id
            )
            
        except (ValidationError, Contract.DoesNotExist) as err:
            return Response({"success": False, "error": err.args[0]}, status=status.HTTP_400_BAD_REQUEST)
  
        return Response(status=status.HTTP_200_OK)
    
    def validate_permissions(self, wallet_hash, pk):
        '''
        validate_permissions will raise a ValidationError if:
            (1) caller is not the order's arbiter
            (2) the order's current status is not REFUND_PENDING
        '''
        prefix = "ValidationError:"

        try:
            caller = Peer.objects.get(wallet_hash=wallet_hash)
            order = Order.objects.get(pk=pk)
            curr_status = Status.objects.filter(order=order).latest('created_at')
        except Peer.DoesNotExist or Order.DoesNotExist as err:
            raise ValidationError(f'{prefix} {err.args[0]}')
        
        if caller.wallet_hash != order.arbiter.wallet_hash:
            raise ValidationError(f'{prefix} Caller must be order arbiter.')
        
        if (curr_status.status != StatusType.REFUND_PENDING):
                raise ValidationError(f'{prefix} Current status of order #{pk} is not {StatusType.REFUND_PENDING.label}.')
