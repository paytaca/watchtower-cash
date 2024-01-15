from rest_framework import status
from rest_framework.views import APIView
from rest_framework.response import Response

from django.core.exceptions import ValidationError
from django.http import Http404

from authentication.token import TokenAuthentication
# from rampp2p.utils.utils import get_trading_fees
import rampp2p.utils as utils
from rampp2p.utils.contract import create_contract
from rampp2p.validators import *
from rampp2p.models import (
    StatusType,
    Order,
    Peer,
    Contract,
    Transaction,
    Recipient,
    Arbiter,
    TradeType
)
from rampp2p.serializers import (
    ContractSerializer, 
    ContractDetailSerializer,
    TransactionSerializer, 
    RecipientSerializer
)

import logging
logger = logging.getLogger(__name__)

class ContractDetailsView(APIView):
    authentication_classes = [TokenAuthentication]

    def get_object(self, pk):
        try:
            return Contract.objects.get(pk=pk)
        except Contract.DoesNotExist:
            raise Http404

    def get(self, _, pk):
        contract = self.get_object(pk)
        serialized_contract = ContractDetailSerializer(contract)
        return Response(serialized_contract.data, status=status.HTTP_200_OK)

class ContractCreateView(APIView):
    authentication_classes = [TokenAuthentication]
    
    def post(self, request):
        try:
            order_pk = request.data.get('order_id')
            arbiter_pk = request.data.get('arbiter_id')
            if order_pk is None or arbiter_pk is None:
                return Response({'error': 'order_id or arbiter_id is required'}, status=status.HTTP_400_BAD_REQUEST)
            
            validate_status(order_pk, StatusType.CONFIRMED)
            order = Order.objects.get(pk=order_pk)
            if not self.has_permissions(order, request.user.wallet_hash):
                return Response(status=status.HTTP_401_UNAUTHORIZED)

            arbiter = Arbiter.objects.get(pk=arbiter_pk)
            params = self.get_params(arbiter.public_key, order)

        except (Order.DoesNotExist, Arbiter.DoesNotExist, ValidationError) as err:
            return Response({'error': err.args[0]}, status=status.HTTP_400_BAD_REQUEST)
        
        generate = False
        address = None
        timestamp = None
        contract = Contract.objects.filter(order__id=order_pk)

        if not contract.exists():
            # Create contract (& address) if not already existing
            contract = Contract.objects.create(order=order)
            generate = True
        else:
            contract = contract.first()
            # (Re)generate contract address if:
            #   - address is None
            #   - arbiter is None
            #   - arbiter has been changed
            if ((contract.address is None) 
                or (order.arbiter is None) 
                or (order.arbiter.id != arbiter.id)):
                generate = True
            else:
                # return contract if already existing
                address = contract.address
        
        timestamp = contract.created_at.timestamp()
        if generate:
            # if contract.address != None:
                # unsubscribe to contract address
            contract.address = None
            contract.save()
            # Execute subprocess
            create_contract(
                order_id=contract.order.id,
                arbiter_pubkey=params['arbiter_pubkey'], 
                seller_pubkey=params['seller_pubkey'], 
                buyer_pubkey=params['buyer_pubkey'],
                timestamp=timestamp
            )
        
        # update order arbiter
        order.arbiter = arbiter
        order.save()
        
        response = {
            'success': True,
            'data': {
                'order': order.id,
                'contract': contract.id,
                'timestamp': timestamp,
                'arbiter_address': order.arbiter.address,
                'buyer_address': params['buyer_address'],
                'seller_address': params['seller_address']
            }
        }
        
        if not (address is None):
            response['data']['contract_address'] = address
        
        return Response(response, status=status.HTTP_200_OK)

    def get_params(self, arbiter_pubkey, order: Order):

        seller_pubkey = None
        buyer_pubkey = None
        seller_address = None
        buyer_address = None

        if order.ad_snapshot.trade_type == TradeType.SELL:
            seller_pubkey = order.ad_snapshot.ad.owner.public_key
            buyer_pubkey = order.owner.public_key
            seller_address = order.ad_snapshot.ad.owner.address
            buyer_address = order.owner.address
        else:
            seller_pubkey = order.owner.public_key
            buyer_pubkey = order.ad_snapshot.ad.owner.public_key
            seller_address = order.owner.address
            buyer_address = order.ad_snapshot.ad.owner.address

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
        }

        return params
    
    def has_permissions(self, order: Order, wallet_hash: str):
        return utils.is_seller(order, wallet_hash)
        
class ContractTransactionsView(APIView):
    authentication_classes = [TokenAuthentication]

    def get_object(self, pk):
        try:
            contract = Contract.objects.get(pk=pk)
        except Contract.DoesNotExist:
            raise Http404
        return contract
    
    def get(self, _, pk):
        contract = self.get_object(pk)
        transactions = Transaction.objects.filter(contract__id=contract.id)

        tx_data = []
        for _, tx in enumerate(transactions):
            tx_outputs = Recipient.objects.filter(transaction__id=tx.id)
            data = {}
            data["txn"] = TransactionSerializer(tx).data
            data["txn"]["outputs"] = RecipientSerializer(tx_outputs, many=True).data
            tx_data.append(data)

        return Response(tx_data, status=status.HTTP_200_OK)

class ContractFeesView(APIView):
    authentication_classes = [TokenAuthentication]

    def get(self, _,):
        total_fee, breakdown = utils.get_trading_fees()
        response = {
            'total': total_fee,
            'breakdown': breakdown
        }
        return Response(response, status=status.HTTP_200_OK)