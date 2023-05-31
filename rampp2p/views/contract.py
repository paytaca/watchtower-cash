from rest_framework import status
from rest_framework.views import APIView
from rest_framework.response import Response
from django.core.exceptions import ValidationError
from django.http import Http404

from rampp2p import utils
from rampp2p.utils import auth
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
        
        generate = False
        address = None
        contract = Contract.objects.get(order__id=pk)

        if not contract.exists():
            contract = ContractSerializer({"order": order.id}).save()
            generate = True
        else:
            # return contract if already existing
            if contract.contract_address is None:
                generate = True
            else:
                address = contract.contract_address
        
        
        if generate:
            # Execute subprocess
            timestamp = contract.created_at.timestamp()
            utils.contract.create(
                order_id=contract.order.id,
                arbiter_pubkey=params['arbiter_pubkey'], 
                seller_pubkey=params['seller_pubkey'], 
                buyer_pubkey=params['buyer_pubkey'],
                timestamp=timestamp
            )
        
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