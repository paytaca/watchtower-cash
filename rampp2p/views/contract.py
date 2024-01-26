from rest_framework import status
from rest_framework.views import APIView
from rest_framework.response import Response

from django.core.exceptions import ValidationError
from django.http import Http404

from authentication.token import TokenAuthentication
import rampp2p.utils as utils
from rampp2p.utils.contract import create_contract
from rampp2p.validators import *
from rampp2p.models import (
    StatusType,
    Order,
    ContractMember,
    Contract,
    Transaction,
    Recipient,
    Arbiter,
    TradeType
)
import rampp2p.serializers as serializers

import logging
logger = logging.getLogger(__name__)

class ContractDetailsView(APIView):
    authentication_classes = [TokenAuthentication]

    def get_object(self, order_id, contract_id):
        try:
            if not order_id and not contract_id:
                raise Contract.DoesNotExist
            query = Contract.objects.all()
            if contract_id:
                query = query.filter(pk=contract_id)
            if order_id:
                query = query.filter(order__id=order_id)
            if query.exists():
                return query.first()
            else:
                raise Contract.DoesNotExist
        except Contract.DoesNotExist:
            raise Http404

    def get(self, request):
        order_id = request.query_params.get('order_id')
        contract_id = request.query_params.get('contract_id')
        contract = self.get_object(order_id, contract_id)
        serialized_contract = serializers.ContractDetailSerializer(contract)
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
            contract_params = self.get_contract_params(arbiter, order)

        except (Order.DoesNotExist, Arbiter.DoesNotExist, ValidationError) as err:
            return Response({'error': err.args[0]}, status=status.HTTP_400_BAD_REQUEST)
        
        address = None
        contract, created = Contract.objects.get_or_create(order=order)
        timestamp = contract.created_at.timestamp()
        if (created or
            contract.address == None or
            contract.order.arbiter == None or
            contract.order.arbiter.id != arbiter.id):
            
            # execute subprocess (generate the contract)
            contract.address = None
            contract.save()

            create_contract(
                order_id=contract.order.id,
                arbiter_pubkey=contract_params['arbiter']['pubkey'], 
                seller_pubkey=contract_params['seller']['pubkey'], 
                buyer_pubkey=contract_params['buyer']['pubkey'],
                timestamp=timestamp
            )

        else:
            address = contract.address
        
        # save contract member pubkeys and addresses
        arbiter_member, _ = ContractMember.objects.update_or_create(
            contract = contract,
            member_type = ContractMember.MemberType.ARBITER,
            defaults={
                'member_ref_id': contract_params['arbiter']['id'],
                'address': contract_params['arbiter']['address'],
                'pubkey': contract_params['arbiter']['pubkey']
            }
        )
        seller_member, _ = ContractMember.objects.update_or_create(
            contract = contract,
            member_type = ContractMember.MemberType.SELLER,
            defaults={
                'member_ref_id': contract_params['seller']['id'],
                'address': contract_params['seller']['address'],
                'pubkey': contract_params['seller']['pubkey']
            }
        )
        buyer_member, _ = ContractMember.objects.update_or_create(
            contract = contract,
            member_type = ContractMember.MemberType.BUYER,
            defaults={
                'member_ref_id': contract_params['buyer']['id'],
                'address': contract_params['buyer']['address'],
                'pubkey': contract_params['buyer']['pubkey']
            }
        )
        members = [arbiter_member, seller_member, buyer_member]
        serialized_members = serializers.ContractMemberSerializer(members, many=True)

        # update order arbiter
        order.arbiter = arbiter
        order.save()
        
        response = {
            'order': order.id,
            'contract': contract.id,
            'timestamp': timestamp,
            'members': serialized_members.data,
            'address': address
        }
        
        return Response(response, status=status.HTTP_200_OK)

    def get_contract_params(self, arbiter, order: Order):

        seller_id = None
        seller_pubkey = None
        seller_address = None
        
        buyer_id = None
        buyer_pubkey = None
        buyer_address = None

        if order.ad_snapshot.trade_type == TradeType.SELL:
            seller_id = order.ad_snapshot.ad.owner.id
            seller_pubkey = order.ad_snapshot.ad.owner.public_key
            seller_address = order.ad_snapshot.ad.owner.address
            
            buyer_id = order.owner.id
            buyer_pubkey = order.owner.public_key
            buyer_address = order.owner.address
        else:
            seller_id = order.owner.id
            seller_pubkey = order.owner.public_key
            seller_address = order.owner.address
            
            buyer_id = order.ad_snapshot.ad.owner.id
            buyer_pubkey = order.ad_snapshot.ad.owner.public_key
            buyer_address = order.ad_snapshot.ad.owner.address

        if (not seller_id or not seller_pubkey or not seller_address or
            not buyer_id or not buyer_pubkey or not buyer_address):
                raise ValidationError('contract parameters are required')
        
        return {
            'arbiter': {
                'id': arbiter.id,
                'pubkey': arbiter.public_key,
                'address': arbiter.address
            },
            'seller': {
                'id': seller_id,
                'pubkey': seller_pubkey,
                'address': seller_address
            },
            'buyer': {
                'id': buyer_id,
                'pubkey': buyer_pubkey,
                'address': buyer_address
            }
        }
    
    def has_permissions(self, order: Order, wallet_hash: str):
        return utils.is_seller(order, wallet_hash)
        
class ContractTransactionsView(APIView):
    authentication_classes = [TokenAuthentication]

    def get_object(self, order_id, contract_id):
        try:
            if not order_id and not contract_id:
                raise Contract.DoesNotExist
            query = Contract.objects.all()
            if contract_id:
                query = query.filter(pk=contract_id)
            if order_id:
                query = query.filter(order__id=order_id)
            if query.exists():
                return query.first()
            else:
                raise Contract.DoesNotExist
        except Contract.DoesNotExist:
            raise Http404

    def get(self, request):
        order_id = request.query_params.get('order_id')
        contract_id = request.query_params.get('contract_id')
        contract = self.get_object(order_id, contract_id)
        transactions = Transaction.objects.filter(contract__id=contract.id)

        tx_data = []
        for _, tx in enumerate(transactions):
            tx_outputs = Recipient.objects.filter(transaction__id=tx.id)
            data = {}
            data["txn"] = serializers.TransactionSerializer(tx).data
            data["txn"]["outputs"] = serializers.RecipientSerializer(tx_outputs, many=True).data
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