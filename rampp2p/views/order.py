from rampp2p.serializers.contract import ContractSerializer
from rest_framework import status
from rest_framework.views import APIView
from rest_framework.response import Response
from django.http import Http404
from django.core.exceptions import ValidationError
from django.db.models import Q
from django.db import IntegrityError
from django.shortcuts import render
from typing import List

from rampp2p import utils
from rampp2p.utils import auth
from rampp2p.viewcodes import ViewCode
from rampp2p.permissions import *
from rampp2p.validators import *
from rampp2p.serializers import (
    OrderSerializer, 
    OrderWriteSerializer, 
    StatusSerializer, 
    ContractSerializer,
    TransactionSerializer
)
from rampp2p.models import (
    Ad,
    StatusType,
    Status,
    Order,
    Peer,
    PaymentMethod,
    Contract,
    Transaction
)
import json
import logging
logger = logging.getLogger(__name__)

'''
  SUBMITTED         = at Order creation
  CONFIRMED         = when crypto is escrowed
  PAID_PENDING      = when crypto buyer clicks "confirm payment"
  PAID              = when crypto seller clicks on "confirm payment"
  CANCEL_APPEALED   = on cancel appeal
  RELEASE_APPEALED  = on release appeal
  REFUND_APPEALED   = on refund appeal
  RELEASED          = on arbiter "release"
  REFUNDED          = on arbiter "refunded"
  CANCELED          = on "cancel order" before status=CONFIRMED || on arbiter "mark canceled, refund"
'''

class OrderListCreate(APIView):

    def get(self, request):
        queryset = Order.objects.all()
        creator = request.query_params.get("creator", None)
        if creator is not None:
            queryset = queryset.filter(creator=creator)
        serializer = OrderSerializer(queryset, many=True)
        return Response(serializer.data, status.HTTP_200_OK)

    def post(self, request):

        try:
            ad_id = request.data.get('ad', None)
            if ad_id is None:
                raise ValidationError('ad_id field is required')
            
            payment_method_ids = request.data.get('payment_methods', None)
            if payment_method_ids is None:
                raise ValidationError('payment_methods field is required')

        except ValidationError as err:
            return Response({'error': err.args[0]}, status=status.HTTP_400_BAD_REQUEST)
        
        try:
            # validate signature
            signature, timestamp, wallet_hash = auth.get_verification_headers(request)
            message = ViewCode.ORDER_CREATE.value + '::' + timestamp
            auth.verify_signature(wallet_hash, signature, message)

            # validate permissions
            self.validate_permissions(wallet_hash, ad_id)
            self.validate_payment_methods_ownership(wallet_hash, payment_method_ids)
        except ValidationError as err:
            return Response({'error': err.args[0]}, status=status.HTTP_403_FORBIDDEN)

        try:
            ad = Ad.objects.get(pk=ad_id)
            owner = Peer.objects.get(wallet_hash=wallet_hash)
        except (Ad.DoesNotExist, Peer.DoesNotExist) as err:
            return Response({'error': err.args[0]}, status=status.HTTP_400_BAD_REQUEST)
        
        data = request.data.copy()
        data['owner'] = owner.id
        data['crypto_currency'] = ad.crypto_currency.id
        data['fiat_currency'] = ad.fiat_currency.id
        data['time_duration_choice'] = ad.time_duration_choice
        serializer = OrderWriteSerializer(data=data)

        if serializer.is_valid():
            order = serializer.save()
            Status.objects.create(
                status=StatusType.SUBMITTED,
                order=Order.objects.get(pk=order.id)
            )
            serializer = OrderSerializer(order)
            return Response(serializer.data, status=status.HTTP_201_CREATED)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    def validate_permissions(self, wallet_hash, pk):
        '''
        Ad owners cannot create orders for their ad
        Arbiters cannot create orders
        '''
        try:
            caller = Peer.objects.get(wallet_hash=wallet_hash)
            ad = Ad.objects.get(pk=pk)
        except Peer.DoesNotExist or Ad.DoesNotExist:
            raise ValidationError('peer or ad DoesNotExist')
        
        if caller.is_arbiter:
            raise ValidationError('caller must not be an arbiter')
        
        if ad.owner.wallet_hash == caller.wallet_hash:
            raise ValidationError('ad owner not allowed to create order for this ad')

    def validate_payment_methods_ownership(self, wallet_hash, payment_method_ids: List[int]):
        '''
        Validates if caller owns the payment methods
        '''

        try:
            caller = Peer.objects.get(wallet_hash=wallet_hash)
        except Peer.DoesNotExist:
            raise ValidationError('peer DoesNotExist')

        payment_methods = PaymentMethod.objects.filter(Q(id__in=payment_method_ids))
        for payment_method in payment_methods:
            if payment_method.owner.wallet_hash != caller.wallet_hash:
                raise ValidationError('invalid payment method, not caller owned')

class OrderListStatus(APIView):
  def get(self, request, pk):
    queryset = Status.objects.filter(order=pk)
    serializer = StatusSerializer(queryset, many=True)
    return Response(serializer.data, status=status.HTTP_200_OK)

class OrderDetail(APIView):
  def get_object(self, pk):
    try:
      return Order.objects.get(pk=pk)
    except Order.DoesNotExist:
      raise Http404

  def get(self, request, pk):
    order = self.get_object(pk)
    response = {
        'order': OrderSerializer(order).data
    }

    order_contract = Contract.objects.filter(order__pk=pk)
    if order_contract.count() > 0:
        order_contract = order_contract.first()
        response['contract'] = ContractSerializer(order_contract).data

    return Response(response, status=status.HTTP_200_OK)

class ConfirmOrder(APIView):
    '''
    Marks the order as ESCROW_PENDING and subscribes to the contract address for incoming and outgoing
    transactions. When the contract address receives a utxo with the correct amount, the order status is
    is set to ESCROWED
    '''
    def post(self, request, pk):
        try:
            # validate signature
            signature, timestamp, wallet_hash = auth.get_verification_headers(request)
            message = ViewCode.ORDER_CONFIRM.value + '::' + timestamp
            auth.verify_signature(wallet_hash, signature, message)

            # validate permissions
            self.validate_permissions(wallet_hash, pk)

        except ValidationError as err:
            return Response({'error': err.args[0]}, status=status.HTTP_403_FORBIDDEN)

        try:
            validate_status_inst_count(StatusType.CONFIRMED, pk)
            validate_status_progression(StatusType.CONFIRMED, pk)

            txid = request.data.get('txid')
            if txid is None:
                raise ValidationError('txid is required')
                
            # contract.contract_address must be set first through GenerateContract endpoint
            contract = Contract.objects.get(order_id=pk)
            if not contract.exists():
                raise ValidationError('order contract does not exist')

            # create ESCROW_PENDING status for order
            status_serializer = StatusSerializer(StatusSerializer(data={
                'status': StatusType.ESCROW_PENDING,
                'order': pk
            }).save())
            
            # TODO: subscribe contract address        

            # notify order participants
            utils.websocket.send_order_update(
                json.dumps(status_serializer.data), 
                contract.contract_address
            )
            
        except (ValidationError, IntegrityError) as err:
            return Response({'error': err.args[0]}, status=status.HTTP_400_BAD_REQUEST)
        
        return Response(status_serializer.data, status=status.HTTP_200_OK)  

    def validate_permissions(self, wallet_hash, pk):
        '''
        Only owners of SELL ads can set order statuses to CONFIRMED.
        Creators of SELL orders skip the order status to CONFIRMED on creation.
        '''

        try:
            caller = Peer.objects.get(wallet_hash=wallet_hash)
            order = Order.objects.get(pk=pk)
        except Peer.DoesNotExist or Order.DoesNotExist:
            raise ValidationError('Peer/Order DoesNotExist')

        if order.ad.trade_type == TradeType.SELL:
            seller = order.ad.owner
            # require caller is seller
            if caller.wallet_hash != seller.wallet_hash:
                raise ValidationError('caller must be seller')
        else:
            raise ValidationError('ad trade_type is not {}'.format(TradeType.SELL))
    
class ForceConfirmOrder(APIView):
    '''
    Manually marks the order as ESCROWED by submitting the transaction id
    for validation (should only be used as fallback when ConfirmOrder endpoint fails).
    '''
    def post(self, request, pk):
        try:
            # validate signature
            signature, timestamp, wallet_hash = auth.get_verification_headers(request)
            message = ViewCode.ORDER_CONFIRM.value + '::' + timestamp
            auth.verify_signature(wallet_hash, signature, message)

            # validate permissions
            self.validate_permissions(wallet_hash, pk)

        except ValidationError as err:
            return Response({'error': err.args[0]}, status=status.HTTP_403_FORBIDDEN)

        try:
            validate_status_inst_count(StatusType.ESCROWED, pk)
            validate_status_progression(StatusType.ESCROWED, pk)

            txid = request.data.get('txid')
            if txid is None:
                raise ValidationError('txid is required')
                
            # contract.contract_address must be set first through GenerateContract endpoint
            contract = Contract.objects.filter(order_id=pk)
            if (contract.count() == 0 or contract.first().contract_address is None):
                raise ValidationError('order contract does not exist')

            contract = contract.first()
            # participants = self.get_order_participants(contract.order)
            utils.validate_transaction(
                txid, 
                action=Transaction.ActionType.FUND,
                contract_id=contract.id, 
                # wallet_hashes=participants
            )
           
        except (ValidationError, IntegrityError) as err:
            return Response({'error': err.args[0]}, status=status.HTTP_400_BAD_REQUEST)
        
        return Response(status=status.HTTP_200_OK)  

    def validate_permissions(self, wallet_hash, pk):
        '''
        Only owners of SELL ads can set order statuses to CONFIRMED.
        Creators of SELL orders skip the order status to CONFIRMED on creation.
        '''

        try:
            caller = Peer.objects.get(wallet_hash=wallet_hash)
            order = Order.objects.get(pk=pk)
        except Peer.DoesNotExist or Order.DoesNotExist:
            raise ValidationError('Peer/Order DoesNotExist')

        if order.ad.trade_type == TradeType.SELL:
            seller = order.ad.owner
            # require caller is seller
            if caller.wallet_hash != seller.wallet_hash:
                raise ValidationError('caller must be seller')
        else:
            raise ValidationError('ad trade_type is not {}'.format(TradeType.SELL))

    # def get_order_participants(self, order: Order):
    #     '''
    #     Returns the wallet hash of the order's seller, buyer and arbiter.
    #     '''
    #     party_a = order.ad.owner.wallet_hash
    #     party_b = order.owner.wallet_hash
    #     arbiter = order.arbiter.wallet_hash
        
    #     return [party_a, party_b, arbiter]
    
class CryptoBuyerConfirmPayment(APIView):
  def post(self, request, pk):

    try:
        # validate signature
        signature, timestamp, wallet_hash = auth.get_verification_headers(request)
        message = ViewCode.ORDER_BUYER_CONF_PAYMENT.value + '::' + timestamp
        auth.verify_signature(wallet_hash, signature, message)

        # validate permissions
        self.validate_permissions(wallet_hash, pk)
    except ValidationError as err:
        return Response({'error': err.args[0]}, status=status.HTTP_403_FORBIDDEN)
    
    try:
        # validations
        validate_status_inst_count(StatusType.PAID_PENDING, pk)
        validate_status_progression(StatusType.PAID_PENDING, pk)
    except ValidationError as err:
      return Response({'error': err.args[0]}, status=status.HTTP_400_BAD_REQUEST)

    # create PAID_PENDING status for order
    serializer = StatusSerializer(data={
        'status': StatusType.PAID_PENDING,
        'order': pk
    })

    if serializer.is_valid():
      stat = StatusSerializer(serializer.save())
      return Response(stat.data, status=status.HTTP_200_OK)        
    return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
  
  def validate_permissions(self, wallet_hash, pk):
    '''
    Only buyers can set order status to PAID_PENDING
    '''

    try:
        caller = Peer.objects.get(wallet_hash=wallet_hash)
        order = Order.objects.get(pk=pk)
    except Peer.DoesNotExist or Order.DoesNotExist:
        raise ValidationError('Peer/Order DoesNotExist')
    
    buyer = None
    if order.ad.trade_type == TradeType.SELL:
       buyer = order.owner
    else:
       buyer = order.ad.owner

    if caller.wallet_hash != buyer.wallet_hash:
        raise ValidationError('caller must be buyer')
    
class CryptoSellerConfirmPayment(APIView):
    def post(self, request, pk):
        
        try:
            # validate signature
            signature, timestamp, wallet_hash = auth.get_verification_headers(request)
            message = ViewCode.ORDER_SELLER_CONF_PAYMENT.value + '::' + timestamp
            auth.verify_signature(wallet_hash, signature, message)

            # validate permissions
            self.validate_permissions(wallet_hash, pk)
        except ValidationError as err:
            return Response({'error': err.args[0]}, status=status.HTTP_403_FORBIDDEN)
        
        try:
            # status validations
            validate_status_inst_count(StatusType.PAID, pk)
            validate_status_progression(StatusType.PAID, pk)
        except ValidationError as err:
            return Response({'error': err.args[0]}, status=status.HTTP_400_BAD_REQUEST)

        # create PAID status for order
        serializer = StatusSerializer(data={
            'status': StatusType.PAID,
            'order': pk
        })

        if serializer.is_valid():
            stat = StatusSerializer(serializer.save())
            return Response(stat.data, status=status.HTTP_200_OK)        
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
  
    def validate_permissions(self, wallet_hash, pk):
        '''
        Only the seller can set the order status to PAID
        '''

        # if ad.trade_type is SELL:
        #      seller is ad creator
        # else 
        #      seller is order creator
        # require(caller == seller)

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

        if caller.wallet_hash != seller.wallet_hash:
            raise ValidationError('caller must be seller')

class CancelOrder(APIView):
    def post(self, request, pk):

        try:
            # validate signature
            signature, timestamp, wallet_hash = auth.get_verification_headers(request)
            message = ViewCode.ORDER_CANCEL.value + '::' + timestamp
            auth.verify_signature(wallet_hash, signature, message)

            # validate permissions
            self.validate_permissions(wallet_hash, pk)
        except ValidationError as err:
            return Response({'error': err.args[0]}, status=status.HTTP_403_FORBIDDEN)

        try:
            # status validations
            validate_status_inst_count(StatusType.CANCELED, pk)
            validate_status_progression(StatusType.CANCELED, pk)
        except ValidationError as err:
            return Response({'error': err.args[0]}, status=status.HTTP_400_BAD_REQUEST)

        # create CANCELED status for order
        serializer = StatusSerializer(data={
            'status': StatusType.CANCELED,
            'order': pk
        })

        if serializer.is_valid():
            stat = StatusSerializer(serializer.save())
            return Response(stat.data, status=status.HTTP_200_OK)        
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
    
    def validate_permissions(self, wallet_hash, pk):
        '''
        CancelOrder must only be callable by the order creator
        '''

        # if caller is not order creator
        #     raise error
        
        try:
            caller = Peer.objects.get(wallet_hash=wallet_hash)
            order = Order.objects.get(pk=pk)
        except Peer.DoesNotExist or Order.DoesNotExist:
            raise ValidationError('Peer/Order DoesNotExist')
        
        if caller.wallet_hash != order.owner.wallet_hash:
           raise ValidationError('caller must be order creator')
