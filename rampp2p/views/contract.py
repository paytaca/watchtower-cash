from rest_framework import status
from rest_framework.views import APIView
from rest_framework.response import Response
from django.core.exceptions import ValidationError

from rampp2p.utils import contract, common
from rampp2p.viewcodes import ViewCode
from rampp2p.permissions import *
from rampp2p.validators import *

from rampp2p.models import (
    StatusType,
    Status,
    Order,
    Peer,
    Contract
)

class CreateContract(APIView):
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
            order = Order.objects.get(pk=pk)
            params = self.get_params(order)
            
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

    def get_params(self, order: Order):
        arbiterPubkey = order.arbiter.public_key
        sellerPubkey = None
        buyerPubkey = None
        sellerAddr = None
        buyerAddr = None

        if order.ad.trade_type == TradeType.SELL:
            sellerPubkey = order.ad.owner.public_key
            buyerPubkey = order.owner.public_key
            sellerAddr = order.ad.owner.address
            buyerAddr = order.owner.address
        else:
            sellerPubkey = order.owner.public_key
            buyerPubkey = order.ad.owner.public_key
            sellerAddr = order.owner.address
            buyerAddr = order.ad.owner.address

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
            seller = order.owner
        
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
        party_b = order.owner.wallet_hash
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
        party_b = order.owner.wallet_hash
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
