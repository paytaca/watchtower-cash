from rest_framework import status
from rest_framework.views import APIView
from rest_framework.response import Response

from django.core.exceptions import ValidationError
from django.http import Http404
from django.conf import settings

from authentication.token import TokenAuthentication
import rampp2p.utils as utils
from rampp2p.utils.contract import create_contract
from rampp2p.validators import *
import rampp2p.models as models
import rampp2p.serializers as serializers

import logging
logger = logging.getLogger(__name__)

class ContractDetailsView(APIView):
    swagger_schema = None
    authentication_classes = [TokenAuthentication]

    def get_object(self, order_id, contract_id):
        try:
            if not order_id and not contract_id:
                raise models.Contract.DoesNotExist
            query = models.Contract.objects.all()
            if contract_id:
                query = query.filter(pk=contract_id)
            if order_id:
                query = query.filter(order__id=order_id)
            if query.exists():
                return query.first()
            else:
                raise models.Contract.DoesNotExist
        except models.Contract.DoesNotExist:
            raise Http404

    def get(self, request):
        order_id = request.query_params.get('order_id')
        contract_id = request.query_params.get('contract_id')
        contract = self.get_object(order_id, contract_id)
        serialized_contract = serializers.ContractDetailSerializer(contract)
        return Response(serialized_contract.data, status=status.HTTP_200_OK)

class ContractCreateView(APIView):
    swagger_schema = None
    authentication_classes = [TokenAuthentication]
    
    def post(self, request):
        try:
            order_pk = request.data.get('order_id')
            arbiter_pk = request.data.get('arbiter_id')
            if order_pk is None or arbiter_pk is None:
                return Response({'error': 'order_id or arbiter_id is required'}, status=status.HTTP_400_BAD_REQUEST)

            validate_status(order_pk, StatusType.CONFIRMED)
            order = models.Order.objects.get(pk=order_pk)
            if not self.has_permissions(order, request.user.wallet_hash):
                return Response(status=status.HTTP_401_UNAUTHORIZED)

            arbiter = models.Arbiter.objects.get(pk=arbiter_pk)
            
            # Require that arbiter is allowed for the order's currency
            currency = order.ad_snapshot.fiat_currency.symbol
            if not arbiter.fiat_currencies.filter(symbol=currency).exists():
                raise ValidationError(f'Arbiter not allowed for currency {currency}')
            
            contract_params = self.get_contract_params(arbiter, order)

        except (models.Order.DoesNotExist, models.Arbiter.DoesNotExist, ValidationError) as err:
            return Response({'error': err.args[0]}, status=status.HTTP_400_BAD_REQUEST)
        
        address = None
        contract, created = models.Contract.objects.get_or_create(order=order)
        timestamp = contract.created_at.timestamp()
        force = request.data.get('force', False)
        if (force or created or
            contract.address == None or
            contract.order.arbiter == None or
            contract.order.arbiter.id != arbiter.id):
            contract.version = settings.SMART_CONTRACT_VERSION
            contract.address = None
            contract.save()
            
            # execute subprocess (generate the contract)
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
        arbiter_member, _ = models.ContractMember.objects.update_or_create(
            contract = contract,
            member_type = models.ContractMember.MemberType.ARBITER,
            defaults={
                'member_ref_id': contract_params['arbiter']['id'],
                'pubkey': contract_params['arbiter']['pubkey'],
                'address': contract_params['arbiter']['address'],
                'address_path': contract_params['arbiter']['address_path']
            }
        )
        seller_member, _ = models.ContractMember.objects.update_or_create(
            contract = contract,
            member_type = models.ContractMember.MemberType.SELLER,
            defaults={
                'member_ref_id': contract_params['seller']['id'],
                'pubkey': contract_params['seller']['pubkey'],
                'address': contract_params['seller']['address'],
                'address_path': contract_params['seller']['address_path']
            }
        )
        buyer_member, _ = models.ContractMember.objects.update_or_create(
            contract = contract,
            member_type = models.ContractMember.MemberType.BUYER,
            defaults={
                'member_ref_id': contract_params['buyer']['id'],
                'pubkey': contract_params['buyer']['pubkey'],
                'address': contract_params['buyer']['address'],
                'address_path': contract_params['buyer']['address_path']
            }
        )
        members = [arbiter_member, seller_member, buyer_member]
        serialized_members = serializers.ContractMemberSerializer(members, many=True)

        # update order arbiter
        order.arbiter = arbiter
        order.save()

        # add arbiter as order member
        member, created = models.OrderMember.objects.get_or_create(order=order, type=models.OrderMember.MemberType.ARBITER)
        member.arbiter = arbiter
        member.save()
    
        response = {
            'order': order.id,
            'contract': contract.id,
            'timestamp': timestamp,
            'members': serialized_members.data,
            'address': address
        }
        
        return Response(response, status=status.HTTP_200_OK)

    def get_contract_params(self, arbiter, order: models.Order):

        seller_id = None
        seller_pubkey = None
        seller_address = None
        seller_address_path = None
        
        buyer_id = None
        buyer_pubkey = None
        buyer_address = None
        buyer_address_path = None

        if order.ad_snapshot.trade_type == models.TradeType.SELL:
            seller_id = order.ad_snapshot.ad.owner.id
            seller_pubkey = order.ad_snapshot.ad.owner.public_key
            seller_address = order.ad_snapshot.ad.owner.address
            seller_address_path = order.ad_snapshot.ad.owner.address_path
            
            buyer_id = order.owner.id
            buyer_pubkey = order.owner.public_key
            buyer_address = order.owner.address
            buyer_address_path = order.owner.address_path
        else:
            seller_id = order.owner.id
            seller_pubkey = order.owner.public_key
            seller_address = order.owner.address
            seller_address_path = order.owner.address_path
            
            buyer_id = order.ad_snapshot.ad.owner.id
            buyer_pubkey = order.ad_snapshot.ad.owner.public_key
            buyer_address = order.ad_snapshot.ad.owner.address
            buyer_address_path = order.ad_snapshot.ad.owner.address_path
        
        return {
            'arbiter': {
                'id': arbiter.id,
                'pubkey': arbiter.public_key,
                'address': arbiter.address,
                'address_path': arbiter.address_path
            },
            'seller': {
                'id': seller_id,
                'pubkey': seller_pubkey,
                'address': seller_address,
                'address_path': seller_address_path
            },
            'buyer': {
                'id': buyer_id,
                'pubkey': buyer_pubkey,
                'address': buyer_address,
                'address_path': buyer_address_path
            }
        }
    
    def has_permissions(self, order: models.Order, wallet_hash: str):
        return utils.is_seller(order, wallet_hash)
        
class ContractTransactionsView(APIView):
    swagger_schema = None
    authentication_classes = [TokenAuthentication]

    def get_object(self, order_id, contract_id):
        try:
            if not order_id and not contract_id:
                raise models.Contract.DoesNotExist
            query = models.Contract.objects.all()
            if contract_id:
                query = query.filter(pk=contract_id)
            if order_id:
                query = query.filter(order__id=order_id)
            if query.exists():
                return query.first()
            else:
                raise models.Contract.DoesNotExist
        except models.Contract.DoesNotExist:
            raise Http404

    def get(self, request):
        order_id = request.query_params.get('order_id')
        contract_id = request.query_params.get('contract_id')
        contract = self.get_object(order_id, contract_id)
        transactions = models.Transaction.objects.filter(contract__id=contract.id)

        tx_data = []
        for _, tx in enumerate(transactions):
            tx_outputs = models.Recipient.objects.filter(transaction__id=tx.id)
            data = {}
            data["txn"] = serializers.TransactionSerializer(tx).data
            data["txn"]["outputs"] = serializers.RecipientSerializer(tx_outputs, many=True).data
            tx_data.append(data)

        return Response(tx_data, status=status.HTTP_200_OK)

class ContractFeesView(APIView):
    swagger_schema = None
    authentication_classes = [TokenAuthentication]

    def get(self, _,):
        total_fee, breakdown = utils.get_trading_fees()
        response = {
            'total': total_fee,
            'breakdown': breakdown
        }
        return Response(response, status=status.HTTP_200_OK)