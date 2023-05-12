from rampp2p.serializers.contract import ContractSerializer
from rest_framework import generics, status
from rest_framework.views import APIView
from rest_framework.response import Response
from django.http import Http404
from django.core.exceptions import ValidationError
from django.db.models import Q
from django.db import IntegrityError
from django.shortcuts import render
from typing import List

import rampp2p.tasks as tasks
from rampp2p.utils import websocket, contract, common

from ..viewcodes import ViewCode

from ..permissions import *
from ..validators import *
from ..base_serializers import (
  OrderSerializer, 
  OrderWriteSerializer, 
  StatusSerializer,
  ReceiptSerializer,
)
from rampp2p.serializers.contract import ContractSerializer

from rampp2p.models import (
  Ad,
  StatusType,
  Status,
  Order,
  Peer,
  PaymentMethod,
  Receipt,
  Contract
)

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

class OrderList(APIView):

    def get(self, request):
        queryset = Order.objects.all()
        creator = request.query_params.get("creator", None)
        if creator is not None:
            queryset = queryset.filter(creator=creator)
        serializer = OrderSerializer(queryset, many=True)
        return Response(serializer.data, status.HTTP_200_OK)

    def post(self, request):

        ad_id = request.data.get('ad', None)
        if ad_id is None:
            return Response({'error': 'ad_id field is None'}, status=status.HTTP_400_BAD_REQUEST)
        
        payment_method_ids = request.data.get('payment_methods', None)
        if payment_method_ids is None:
            return Response({'error': 'payment_methods field is None'}, status=status.HTTP_400_BAD_REQUEST)

        try:
            # validate signature
            pubkey, signature, timestamp, wallet_hash = common.get_verification_headers(request)
            message = ViewCode.ORDER_CREATE.value + '::' + timestamp
            common.verify_signature(wallet_hash, pubkey, signature, message)

            # validate permissions
            self.validate_permissions(wallet_hash, ad_id)
            self.validate_payment_methods_ownership(wallet_hash, payment_method_ids)
        except ValidationError as err:
            return Response({'error': err.args[0]}, status=status.HTTP_403_FORBIDDEN)
        
        ad = Ad.objects.get(pk=ad_id)
        creator = Peer.objects.get(wallet_hash=wallet_hash)

        data = request.data.copy()
        data['creator'] = creator.id
        data['crypto_currency'] = ad.crypto_currency.id
        data['fiat_currency'] = ad.fiat_currency.id
        serializer = OrderWriteSerializer(data=data)

        if serializer.is_valid():
            
            # if ad type is BUY:
            #   bch is escrowed and order skips to status CONFIRMED
            statusType = StatusType.SUBMITTED
            if ad.trade_type == TradeType.BUY:
                # TODO escrow funds
                statusType = StatusType.CONFIRMED

            order = serializer.save()
            Status.objects.create(
                status=statusType,
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

        # if caller is arbiter
        #   raise error
        # else if caller is ad owner
        #   raise error

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

        # for payment_method in  payment_methods:
        #    if payment_method.owner != caller
        #           raise error

        try:
            caller = Peer.objects.get(wallet_hash=wallet_hash)
        except Peer.DoesNotExist:
            raise ValidationError('peer DoesNotExist')

        payment_methods = PaymentMethod.objects.filter(Q(id__in=payment_method_ids))
        for payment_method in payment_methods:
            if payment_method.owner.wallet_hash != caller.wallet_hash:
                raise ValidationError('invalid payment method, not caller owned')

class OrderStatusList(APIView):
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

class GenerateContract(APIView):
    def post(self, request, pk):
        
        try:
            # signature validation
            pubkey, signature, timestamp, wallet_hash = common.get_verification_headers(request)
            message = ViewCode.ORDER_CONFIRM.value + '::' + timestamp
            common.verify_signature(wallet_hash, pubkey, signature, message)

            # permission validations
            self.validate_permissions(wallet_hash, pk)

        except Exception as err:
            return Response({'error': err.args[0]}, status=status.HTTP_403_FORBIDDEN)
        
        try:
            # no need to generate contract address 
            # when order is already >= CONFIRMED 
            validate_status(pk, StatusType.SUBMITTED)

            params = self.get_params(request)
            order = Order.objects.get(pk=pk)
            
        except Exception as err:
            return Response({'error': err.args[0]}, status=status.HTTP_400_BAD_REQUEST)
        
        args = {
            'order': order,
            'arbiter_address': order.arbiter.arbiter_address,
            'buyer_address': params['buyerAddr'],
            'seller_address': params['sellerAddr']
        }

        contract_obj = Contract.objects.filter(order__id=pk)
        if contract_obj.count() == 0:
            contract_obj = Contract.objects.create(**args)

            # execute subprocess
            contract.create(
                contract_obj.id,
                wallet_hash,
                arbiterPubkey=params['arbiterPubkey'], 
                sellerPubkey=params['sellerPubkey'], 
                buyerPubkey=params['buyerPubkey']
            )

        else:
            contract_obj = contract_obj.first()
            args['contract_address'] = contract_obj.contract_address
        
        args['contract_id'] = contract_obj.id
        args['order'] = order.id
        
        return Response(args, status=status.HTTP_200_OK)

    def get_params(self, request):
        arbiterPubkey = request.data.get('arbiter_pubkey', None)
        sellerPubkey = request.data.get('seller_pubkey', None)
        buyerPubkey = request.data.get('buyer_pubkey', None)
        sellerAddr = request.data.get('seller_addr', None)
        buyerAddr = request.data.get('buyer_addr', None)

        if (arbiterPubkey is None or 
            sellerPubkey is None or 
            buyerPubkey is None or
            sellerAddr is None or
            buyerAddr is None):
            raise ValidationError('contract parameters are required')
        
        params = {
            'arbiterPubkey': arbiterPubkey,
            'sellerPubkey': sellerPubkey,
            'buyerPubkey': buyerPubkey,
            'sellerAddr': sellerAddr,
            'buyerAddr': buyerAddr
        }

        return params
    
    def validate_permissions(self, wallet_hash, pk):
        '''
        Only owners of SELL ads can set order statuses to CONFIRMED.
        Creators of SELL orders skip the order status to CONFIRMED on creation.
        '''

        # check if ad type is SELL
        # if ad type is SELL:
        #    require caller = ad owner
        # else
        #    raise error

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

class ConfirmOrder(APIView):
    def post(self, request, pk):
        
        data = request.data

        try:
            # validate signature
            pubkey, signature, timestamp, wallet_hash = common.get_verification_headers(request)
            message = ViewCode.ORDER_CONFIRM.value + '::' + timestamp
            common.verify_signature(wallet_hash, pubkey, signature, message)

            # validate permissions
            self.validate_permissions(wallet_hash, pk)

        except ValidationError as err:
            return Response({'error': err.args[0]}, status=status.HTTP_403_FORBIDDEN)

        try:
            validate_status_inst_count(StatusType.CONFIRMED, pk)
            validate_status_progression(StatusType.CONFIRMED, pk)

            if data.get('txid') is None:
                raise ValidationError('txid is required')
            
            # contract.contract_address must be set first through GenerateContract endpoint
            contract = Contract.objects.filter(order_id=pk)
            if (contract.count() == 0 or contract.first().contract_address is None):
                raise ValidationError('order contract does not exist')

            contract = contract.first()
            
            # # Verify that tx exists, its recipient is contract address, and tx amount is correct
            # order = Order.objects.get(pk=pk)
            # transaction = Transaction.objects.filter(txid=contract.txid).first()
            # if transaction is None:
            #     raise ValidationError('transaction with txid DoesNotExist')
            # if transaction.address != contract.contract_address:
            #     raise ValidationError('transaction.address does not match contract address')
            # if transaction.amount != order.crypto_amount:
            #     raise ValidationError('transaction.amount does not match contract order amount')

            contract.txid = data.get('txid')
            contract = ContractSerializer(contract.save())

        except (ValidationError, IntegrityError) as err:
            return Response({'error': err.args[0]}, status=status.HTTP_400_BAD_REQUEST)

        # create CONFIRMED status for order
        serializer = StatusSerializer(data={
            'status': StatusType.CONFIRMED,
            'order': pk
        })

        orderstat = None
        if serializer.is_valid():
            orderstat = StatusSerializer(serializer.save())  
        else:
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
        
        return Response({'status': orderstat.data}, status=status.HTTP_200_OK)  

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

class CryptoBuyerConfirmPayment(APIView):
  def post(self, request, pk):

    try:
        # validate signature
        pubkey, signature, timestamp, wallet_hash = common.get_verification_headers(request)
        message = ViewCode.ORDER_BUYER_CONF_PAYMENT.value + '::' + timestamp
        common.verify_signature(wallet_hash, pubkey, signature, message)

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

    # if ad.trade_type is SELL
    #   buyer is the BUY order creator
    # else (ad.trade_type is BUY)
    #   buyer is the ad creator
    # require(caller = buyer)

    try:
        caller = Peer.objects.get(wallet_hash=wallet_hash)
        order = Order.objects.get(pk=pk)
    except Peer.DoesNotExist or Order.DoesNotExist:
        raise ValidationError('Peer/Order DoesNotExist')
    
    buyer = None
    if order.ad.trade_type == TradeType.SELL:
       buyer = order.creator
    else:
       buyer = order.ad.owner

    if caller.wallet_hash != buyer.wallet_hash:
        raise ValidationError('caller must be buyer')
    
class CryptoSellerConfirmPayment(APIView):
    def post(self, request, pk):
        
        try:
            # validate signature
            pubkey, signature, timestamp, wallet_hash = common.get_verification_headers(request)
            message = ViewCode.ORDER_SELLER_CONF_PAYMENT.value + '::' + timestamp
            common.verify_signature(wallet_hash, pubkey, signature, message)

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
            seller = order.creator

        if caller.wallet_hash != seller.wallet_hash:
            raise ValidationError('caller must be seller')

class ReleaseCrypto(APIView):
    def post(self, request, pk):

        try:
            # validate signature
            pubkey, signature, timestamp, wallet_hash = common.get_verification_headers(request)
            message = ViewCode.ORDER_RELEASE.value + '::' + timestamp
            common.verify_signature(wallet_hash, pubkey, signature, message)

            # validate permissions
            caller_id = self.validate_permissions(wallet_hash, pk)
        except ValidationError as err:
            return Response({'error': err.args[0]}, status=status.HTTP_403_FORBIDDEN)

        try:
            # status validations
            validate_status_inst_count(StatusType.RELEASED, pk)
            validate_exclusive_stats(StatusType.RELEASED, pk)
            validate_status_progression(StatusType.RELEASED, pk)
            
            order = self.get_object(pk)
            contract_obj = Contract.objects.filter(order__id=pk).first()
            params = self.get_params(request)
            
            action = 'seller-release'
            if caller_id == 'ARBITER':
                action = 'arbiter-release'

            # execute subprocess
            parties = self.get_parties(order)
            contract.release(
                order.id,
                contract_obj.id,
                parties,
                action=action,
                arbiterPubkey=params['arbiterPubkey'], 
                sellerPubkey=params['sellerPubkey'], 
                buyerPubkey=params['buyerPubkey'],
                callerSig=params['callerSig'], 
                recipientAddr=contract_obj.buyer_address, 
                arbiterAddr=contract_obj.arbiter_address,
                amount=order.crypto_amount
            )
            
        except Exception as err:
            return Response({'error': err.args[0]}, status=status.HTTP_400_BAD_REQUEST)

        return Response(status=status.HTTP_200_OK)        
    
    def validate_permissions(self, wallet_hash, pk):
        '''
        ReleaseCrypto must only be callable by seller
        or arbiter if order's status is RELEASE_APPEALED or REFUND_APPEALED
        '''

        # if caller == order.arbiter
        #   require(order.status is RELEASE_APPEALED or REFUND_APPEALED)
        # else if order.trade_type is SELL
        #   seller is ad creator
        # else
        #   seller is order creator
        # require(caller = seller)

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
            seller = order.creator
        
        if seller is not None and seller.wallet_hash != caller.wallet_hash:
           raise ValidationError('caller must be seller')
        
        return caller_id

    def get_object(self, pk):
        try:
            return Order.objects.get(pk=pk)
        except Order.DoesNotExist as err:
            raise err

    def get_contract(self, order: Order, **kwargs):
        arbiterPubkey = kwargs.get('arbiterPubkey')
        sellerPubkey = kwargs.get('sellerPubkey')
        buyerPubkey = kwargs.get('buyerPubkey')

        contract = Contract(arbiterPubkey, sellerPubkey, buyerPubkey)
        if order.contract_address != contract.address:
            raise ValidationError('order contract address mismatch')
        return contract

    def get_params(self, request):
        arbiterPubkey = request.data.get('arbiter_pubkey', None)
        sellerPubkey = request.data.get('seller_pubkey', None)
        buyerPubkey = request.data.get('buyer_pubkey', None)
        callerPubkey = request.data.get('caller_pubkey', None)
        callerSig = request.data.get('caller_sig', None)

        if (arbiterPubkey is None or 
                sellerPubkey is None or 
                    buyerPubkey is None):
            raise ValidationError('arbiter, seller and buyer public keys are required')
        
        params = {
            'arbiterPubkey': arbiterPubkey,
            'sellerPubkey': sellerPubkey,
            'buyerPubkey': buyerPubkey,
            'callerPubkey': callerPubkey,
            'callerSig': callerSig
        }
        return params
    
    def get_parties(self, order: Order):
        '''
        Returns the wallet hash of the order's seller, buyer and arbiter.
        '''
        party_a = order.ad.owner.wallet_hash
        party_b = order.creator.wallet_hash
        arbiter = order.arbiter.wallet_hash
        
        return [party_a, party_b, arbiter]
    
class RefundCrypto(APIView):
    def post(self, request, pk):

        try:
            # validate signature
            pubkey, signature, timestamp, wallet_hash = common.get_verification_headers(request)
            message = ViewCode.ORDER_REFUND.value + '::' + timestamp
            common.verify_signature(wallet_hash, pubkey, signature, message)

            # validate permissions
            self.validate_permissions(wallet_hash, pk)
        
            # status validations
            validate_status_inst_count(StatusType.REFUNDED, pk)
            validate_exclusive_stats(StatusType.REFUNDED, pk)
            validate_status_progression(StatusType.REFUNDED, pk)

            order = self.get_object(pk)
            contract_obj = Contract.objects.filter(order__id=pk).first()
            params = self.get_params(request)

            # execute subprocess
            parties = self.get_parties(order)
            contract.refund(
                order.id,
                contract_obj.id,
                parties,
                arbiterPubkey=params['arbiterPubkey'], 
                sellerPubkey=params['sellerPubkey'], 
                buyerPubkey=params['buyerPubkey'],
                callerSig=params['callerSig'], 
                recipientAddr=contract_obj.seller_address, 
                arbiterAddr=contract_obj.arbiter_address,
                amount=order.crypto_amount
            )

        except ValidationError as err:
            return Response({'error': err.args[0]}, status=status.HTTP_400_BAD_REQUEST)
        
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

    def get_parties(self, order: Order):
        '''
        Returns the wallet hash of the order's seller, buyer and arbiter.
        '''
        party_a = order.ad.owner.wallet_hash
        party_b = order.creator.wallet_hash
        arbiter = order.arbiter.wallet_hash
        
        return [party_a, party_b, arbiter]

    def get_params(self, request):
        arbiterPubkey = request.data.get('arbiter_pubkey', None)
        sellerPubkey = request.data.get('seller_pubkey', None)
        buyerPubkey = request.data.get('buyer_pubkey', None)
        callerSig = request.data.get('arbiter_sig', None)

        if (arbiterPubkey is None or 
                sellerPubkey is None or 
                    buyerPubkey is None):
            raise ValidationError('arbiter, seller and buyer public keys are required')
        
        params = {
            'arbiterPubkey': arbiterPubkey,
            'sellerPubkey': sellerPubkey,
            'buyerPubkey': buyerPubkey,
            'callerSig': callerSig
        }
        return params

class CancelOrder(APIView):
    def post(self, request, pk):

        try:
            # validate signature
            pubkey, signature, timestamp, wallet_hash = common.get_verification_headers(request)
            message = ViewCode.ORDER_CANCEL.value + '::' + timestamp
            common.verify_signature(wallet_hash, pubkey, signature, message)

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
        
        if caller.wallet_hash != order.creator.wallet_hash:
           raise ValidationError('caller must be order creator')
