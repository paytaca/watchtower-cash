from rest_framework import status
from rest_framework.views import APIView
from rest_framework.response import Response
from django.core.exceptions import ValidationError
from django.http import Http404

from rampp2p import utils
from rampp2p.utils import contract, auth, transaction
from rampp2p.viewcodes import ViewCode
from rampp2p.permissions import *
from rampp2p.validators import *

from rampp2p.models import (
    StatusType,
    Status,
    Order,
    Peer,
    Contract,
    Transaction,
    Recipient
)

from rampp2p.serializers import (
    ContractSerializer, 
    TransactionSerializer, 
    RecipientSerializer
)

import logging
logger = logging.getLogger(__name__)

class ContractList(APIView):
    def get(self, request):
        queryset = Contract.objects.all()

        # TODO pagination

        serializer = ContractSerializer(queryset, many=True)
        return Response(serializer.data, status.HTTP_200_OK)

class ContractDetail(APIView):
    def get_object(self, pk):
        try:
            return Contract.objects.get(pk=pk)
        except Contract.DoesNotExist:
            raise Http404

    def get(self, request, pk):
        contract_instance = self.get_object(pk)
        contract_serializer = ContractSerializer(contract_instance)

        transactions = Transaction.objects.filter(contract__id=contract_instance.id)

        tx_data = []
        for index, tx in enumerate(transactions):
            tx_outputs = Recipient.objects.filter(transaction__id=tx.id)
            data = {}
            data[index] = TransactionSerializer(tx).data
            data[index]["outputs"] = RecipientSerializer(tx_outputs, many=True).data
            tx_data.append(data)

        response = {
            "contract": contract_serializer.data,
            "transactions": tx_data
        }
        return Response(response, status=status.HTTP_200_OK)

class CreateContract(APIView):
    def post(self, request, pk):
        
        try:
            # signature validation
            signature, timestamp, wallet_hash = auth.get_verification_headers(request)
            message = ViewCode.ORDER_CONFIRM.value + '::' + timestamp
            auth.verify_signature(wallet_hash, signature, message)

            # permission validations
            self.validate_permissions(wallet_hash, pk)

        except ValidationError as err:
            return Response({'error': err.args[0]}, status=status.HTTP_403_FORBIDDEN)
        
        try:
            validate_status(pk, StatusType.SUBMITTED)
            order = Order.objects.get(pk=pk)
            params = self.get_params(order)

        except (Order.DoesNotExist, ValidationError) as err:
            return Response({'error': err.args[0]}, status=status.HTTP_400_BAD_REQUEST)

        contract_obj = Contract.objects.filter(order__id=pk)
        gen_contract_address = False
        contract_address = None
        if contract_obj.count() == 0:
            
            contract_obj = Contract.objects.create(order=order)
            gen_contract_address = True
        else:
            # return contract if already existing
            contract_obj = contract_obj.first()
            if contract_obj.contract_address is None:
                gen_contract_address = True
            else:
                contract_address = contract_obj.contract_address
        
        timestamp = contract_obj.created_at.timestamp()
        if gen_contract_address:
            # execute subprocess
            logger.warning('generating contract address')
            participants = self.get_order_participants(order)
            contract.create(
                contract_obj.id,
                participants,
                arbiter_pubkey=params['arbiter_pubkey'], 
                seller_pubkey=params['seller_pubkey'], 
                buyer_pubkey=params['buyer_pubkey'],
                timestamp=timestamp
            )
        
        response = {
            'success': True,
            'data': {
                'order': order.id,
                'contract_id': contract_obj.id,
                'timestamp': timestamp,
                'arbiter_address': order.arbiter.address,
                'buyer_address': params['buyer_address'],
                'seller_address': params['seller_address']
            }
        }
        
        if not (contract_address is None):
            response['data']['contract_address'] = contract_address
        
        return Response(response, status=status.HTTP_200_OK)

    def get_params(self, order: Order):

        arbiter_pubkey = order.arbiter.public_key
        seller_pubkey = None
        buyer_pubkey = None
        seller_address = None
        buyer_address = None

        if order.ad.trade_type == TradeType.SELL:
            seller_pubkey = order.ad.owner.public_key
            buyer_pubkey = order.owner.public_key
            seller_address = order.ad.owner.address
            buyer_address = order.owner.address
        else:
            seller_pubkey = order.owner.public_key
            buyer_pubkey = order.ad.owner.public_key
            seller_address = order.owner.address
            buyer_address = order.ad.owner.address

        if (arbiter_pubkey is None or 
            seller_pubkey is None or 
            buyer_pubkey is None or
            seller_address is None or
            buyer_address is None):
            raise ValidationError('contract parameters are required')
        
        params = {
            'arbiter_pubkey': arbiter_pubkey,
            'seller_pubkey': seller_pubkey,
            'buyer_pubkey': buyer_pubkey,
            'seller_address': seller_address,
            'buyer_address': buyer_address,
            # 'contract_hash': contract_hash
        }

        return params
    
    def validate_permissions(self, wallet_hash, pk):
        '''
        Owners of SELL ads can set order statuses to CONFIRMED.
        Owners of orders for sell ads can set order statuses to CONFIRMED.
        '''

        try:
            caller = Peer.objects.get(wallet_hash=wallet_hash)
            order = Order.objects.get(pk=pk)
        except Peer.DoesNotExist or Order.DoesNotExist:
            raise ValidationError('Peer/Order DoesNotExist')

        seller = None
        if order.ad.trade_type == TradeType.SELL:
            seller = order.ad.owner
        else:
            seller = order.owner
    
        # require caller is seller
        if caller.wallet_hash != seller.wallet_hash:
            raise ValidationError('caller must be seller')

    def get_order_participants(self, order: Order):
        '''
        Returns the wallet hash of the order's seller, buyer and arbiter.
        '''
        party_a = order.ad.owner.wallet_hash
        party_b = order.owner.wallet_hash
        arbiter = order.arbiter.wallet_hash
        
        return [party_a, party_b, arbiter]
    
class ReleaseCrypto(APIView):
    def post(self, request, pk):

        try:
            # validate signature
            signature, timestamp, wallet_hash = auth.get_verification_headers(request)
            message = ViewCode.ORDER_RELEASE.value + '::' + timestamp
            auth.verify_signature(wallet_hash, signature, message)

            # validate permissions
            caller_id = self.validate_permissions(wallet_hash, pk)
        except ValidationError as err:
            return Response({"success": False, "error": err.args[0]}, status=status.HTTP_403_FORBIDDEN)

        try:
            # status validations
            validate_status_inst_count(StatusType.RELEASED, pk)
            validate_exclusive_stats(StatusType.RELEASED, pk)
            validate_status_progression(StatusType.RELEASED, pk)
            
            order = self.get_object(pk)
            contract_id = Contract.objects.values('id').filter(order__id=pk).first()['id']
            
            txid = request.data.get('txid')
            if txid is None:
                raise ValidationError('txid field is required')

            # verify txid
            participants = self.get_order_participants(order)
            utils.validate_transaction(
                txid, 
                action=Transaction.ActionType.RELEASE,
                contract_id=contract_id, 
                wallet_hashes=participants
            )
            
        except ValidationError as err:
            return Response({"success": False, "error": err.args[0]}, status=status.HTTP_400_BAD_REQUEST)
  
        return Response(status=status.HTTP_200_OK)
    
    def validate_permissions(self, wallet_hash, pk):
        '''
        ReleaseCrypto must only be callable by seller
        or arbiter if order's status is RELEASE_APPEALED or REFUND_APPEALED
        '''

        try:
            caller = Peer.objects.get(wallet_hash=wallet_hash)
            order = Order.objects.get(pk=pk)
            curr_status = Status.objects.filter(order=order).latest('created_at')
        except Peer.DoesNotExist or Order.DoesNotExist:
            raise ValidationError('Peer/Order DoesNotExist')
        
        seller = None
        caller_id = 'SELLER'
        if caller.wallet_hash == order.arbiter.wallet_hash:
           caller_id = 'ARBITER'
           if (curr_status.status != StatusType.RELEASE_APPEALED and 
               curr_status.status != StatusType.REFUND_APPEALED):
              raise ValidationError('arbiter intervention but no order release/refund appeal')
        elif order.ad.trade_type == TradeType.SELL:
            seller = order.ad.owner
        else:
            seller = order.owner
        
        if seller is not None and seller.wallet_hash != caller.wallet_hash:
           raise ValidationError('caller must be seller')
        
        return caller_id

    def get_object(self, pk):
        try:
            return Order.objects.get(pk=pk)
        except Order.DoesNotExist as err:
            raise err

    def get_order_participants(self, order: Order):
        '''
        Returns the wallet hash of the order's seller, buyer and arbiter.
        '''
        party_a = order.ad.owner.wallet_hash
        party_b = order.owner.wallet_hash
        arbiter = order.arbiter.wallet_hash
        
        return [party_a, party_b, arbiter]
    
class RefundCrypto(APIView):
    def post(self, request, pk):
        
        try:
            # validate signature
            signature, timestamp, wallet_hash = auth.get_verification_headers(request)
            message = ViewCode.ORDER_REFUND.value + '::' + timestamp
            auth.verify_signature(wallet_hash, signature, message)

            # validate permissions
            self.validate_permissions(wallet_hash, pk)
        
            # status validations
            validate_status_inst_count(StatusType.REFUNDED, pk)
            validate_exclusive_stats(StatusType.REFUNDED, pk)
            validate_status_progression(StatusType.REFUNDED, pk)

            order = self.get_object(pk)
            contract_id = Contract.objects.values('id').filter(order__id=pk).first()['id']

            txid = request.data.get('txid')
            if txid is None:
                raise ValidationError('txid field is required')

            # verify txid
            participants = self.get_order_participants(order)
            utils.validate_transaction(
                txid, 
                action=Transaction.ActionType.REFUND,
                contract_id=contract_id, 
                wallet_hashes=participants
            )
            
        except ValidationError as err:
            return Response({"success": False, "error": err.args[0]}, status=status.HTTP_400_BAD_REQUEST)
        
        return Response(status=status.HTTP_200_OK)
    
    def validate_permissions(self, wallet_hash, pk):
        '''
        RefundCrypto should be callable only by the arbiter when
        order status is CANCEL_APPEALED, RELEASE_APPEALED, or REFUND_APPEALED
        '''
        try:
            caller = Peer.objects.get(wallet_hash=wallet_hash)
            order = Order.objects.get(pk=pk)
            curr_status = Status.objects.filter(order=order).latest('created_at')
        except (Peer.DoesNotExist, Order.DoesNotExist) as err:
            raise ValidationError(err.args[0])
        
        if caller.wallet_hash != order.arbiter.wallet_hash:
           raise ValidationError('caller must be arbiter')
        else:
           if (curr_status.status != StatusType.CANCEL_APPEALED and
               curr_status.status != StatusType.RELEASE_APPEALED and
               curr_status.status != StatusType.REFUND_APPEALED):
              raise ValidationError('status must be CANCEL_APPEALED | RELEASE_APPEALED | REFUND_APPEALED for this action')

    def get_object(self, pk):
        try:
            return Order.objects.get(pk=pk)
        except Order.DoesNotExist as err:
            raise err

    def get_order_participants(self, order: Order):
        '''
        Returns the wallet hash of the order's seller, buyer and arbiter.
        '''
        party_a = order.ad.owner.wallet_hash
        party_b = order.owner.wallet_hash
        arbiter = order.arbiter.wallet_hash
        
        return [party_a, party_b, arbiter]