from rest_framework import status, viewsets
from rest_framework.response import Response
from rest_framework.decorators import action

from django.http import Http404
from django.conf import settings
from django.db import IntegrityError, transaction
from django.core.exceptions import ValidationError

from authentication.token import TokenAuthentication
from authentication.permissions import RampP2PIsAuthenticated

from rampp2p.utils.fees import get_trading_fees
import rampp2p.utils as utils
import rampp2p.models as models
import rampp2p.serializers as serializers
import rampp2p.utils.websocket as websocket

from rampp2p.validators import *
from rampp2p.utils.contract import create_contract
from rampp2p.utils.transaction import validate_transaction

import logging
logger = logging.getLogger(__name__)

class ContractViewSet(viewsets.GenericViewSet):
    authentication_classes = [TokenAuthentication]
    permission_classes = [RampP2PIsAuthenticated]
    serializer_class = serializers.BaseContractSerializer
    queryset = models.Contract.objects.all()

    def retrieve(self, request, pk):
        try:
            contract = self.get_queryset().get(pk=pk)
            serialized_contract = serializers.ContractSerializer(contract)
            return Response(serialized_contract.data, status=status.HTTP_200_OK)
        except models.Contract.DoesNotExist:
            raise Http404
    
    @action(detail=True, methods=['get'])
    def retrieve_by_order(self, request, pk):
        try:
            contract = self.get_queryset().filter(order__id=pk)
            if not contract.exists():
                raise models.Contract.DoesNotExist
            contract = contract.first()
            serialized_contract = serializers.ContractSerializer(contract)
            return Response(serialized_contract.data, status=status.HTTP_200_OK)
        except models.Contract.DoesNotExist:
            raise Http404

    def create(self, request):
        try:
            version = request.headers.get('version')
            min_required_version = '0.21.0'
            is_compatible = utils.is_min_version_compatible(min_required_version, version)
            if not is_compatible:
                return Response({ 'error' : f'Invalid app version {version}. Min required version is {min_required_version}.' }, status=status.HTTP_400_BAD_REQUEST )

            order_pk = request.data.get('order_id')
            arbiter_pk = request.data.get('arbiter_id')
            if order_pk is None or arbiter_pk is None:
                return Response({'error': 'order_id or arbiter_id is required'}, status=status.HTTP_400_BAD_REQUEST)

            validate_status(order_pk, StatusType.CONFIRMED)

            order = models.Order.objects.get(pk=order_pk)

            # Require that user is seller
            if not order.is_seller(request.user.wallet_hash):
                raise ValidationError('Buyer not allowed to perform this action')

            arbiter = models.Arbiter.objects.get(pk=arbiter_pk)
            
            # Require that arbiter is allowed for the order's currency
            currency = order.ad_snapshot.fiat_currency.symbol
            if not arbiter.fiat_currencies.filter(symbol=currency).exists():
                raise ValidationError(f'Arbiter not allowed for currency {currency}')
            
            contract_params = self._get_contract_params(arbiter, order)
        
            with transaction.atomic():
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
                    
                    _, fees = get_trading_fees(trade_amount=order.trade_amount)
                    contract.arbitration_fee = fees['arbitration_fee']
                    contract.service_fee = fees['service_fee']
                    contract.contract_fee = fees['contract_fee']
                    contract.save()
                    
                    # Execute subprocess (generate the contract)
                    create_contract(
                        order_id=contract.order.id,
                        arbiter_pubkey=contract_params['arbiter']['pubkey'], 
                        seller_pubkey=contract_params['seller']['pubkey'], 
                        buyer_pubkey=contract_params['buyer']['pubkey'],
                        timestamp=timestamp,
                        service_fee=fees['service_fee'],
                        arbitration_fee=fees['arbitration_fee']
                    )
                else:
                    address = contract.address
                
                # Save contract member pubkeys and addresses
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

                # Update order arbiter
                order.arbiter = arbiter
                order.save()

                # Add arbiter as order member
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

        except (models.Order.DoesNotExist, models.Arbiter.DoesNotExist, ValidationError) as err:
            return Response({'error': err.args[0]}, status=status.HTTP_400_BAD_REQUEST)

    @action(detail=True, methods=['get'])
    def transactions(self, request, pk):
        try:
            contract = self.get_queryset().get(pk=pk)
            tx_data = self._retrieve_transactions(contract.id)
            return Response(tx_data, status=status.HTTP_200_OK)
        except models.Contract.DoesNotExist:
                raise Http404
    
    @action(detail=True, methods=['get'])
    def transactions_by_order(self, request, pk):
        try:
            contract = self.get_queryset().filter(order__id=pk)
            if not contract.exists():
                raise models.Contract.DoesNotExist
            contract = contract.first()
            tx_data = self._retrieve_transactions(contract.id)
            return Response(tx_data, status=status.HTTP_200_OK)
        except models.Contract.DoesNotExist:
            raise Http404

    @action(detail=False, methods=['get'])
    def fees(self, request):
        total_fee, breakdown = get_trading_fees()
        response = { 'total': total_fee, 'breakdown': breakdown }
        return Response(response, status=status.HTTP_200_OK)
    
    @action(detail=True, method='get')
    def contract_fees(self, request, pk):
        try:
            order = models.Order.objects.get(id=pk)
            contract = models.Contract.objects.get(order__id=order.id)
            _, breakdown = get_trading_fees(trade_amount=order.trade_amount)
            contract_fee = breakdown['contract_fee']
            service_fee = contract.service_fee
            arbitration_fee = contract.arbitration_fee

            total_fee = contract_fee + service_fee + arbitration_fee

            breakdown = {
                'contract_fee': contract_fee,
                'service_fee': service_fee,
                'arbitration_fee': arbitration_fee
            }
            response = { 'total': total_fee, 'breakdown':  breakdown }

            return Response(response, status=status.HTTP_200_OK)
        except (models.Order.DoesNotExist, models.Contract.DoesNotExist) as err:
            return Response({'error': err.args[0]}, status=status.HTTP_400_BAD_REQUEST)

    @action(detail=True, methods=['post'])
    def pending_escrow(self, request, pk):
        '''Creates a status ESCROW_PENDING for a given order. Callable only by the order's seller.'''

        wallet_hash = request.user.wallet_hash
        try:
            order = models.Order.objects.get(pk=pk)        

            # Require user is seller
            seller = None
            if order.ad_snapshot.trade_type == models.TradeType.SELL:
                seller = order.ad_snapshot.ad.owner
            else:
                seller = order.owner
            if wallet_hash != seller.wallet_hash:
                raise ValidationError('Caller must be seller.')

            validate_status(pk, StatusType.CONFIRMED)
            validate_status_inst_count(StatusType.ESCROW_PENDING, pk)
            validate_status_progression(StatusType.ESCROW_PENDING, pk)

            contract = models.Contract.objects.get(order__id=pk)
            
            # Create ESCROW_PENDING status for order
            status_serializer = serializers.StatusSerializer(data={
                'status': StatusType.ESCROW_PENDING, 
                'order': pk,
                'created_by': wallet_hash
            })
            if status_serializer.is_valid():
                status_serializer = serializers.StatusReadSerializer(status_serializer.save())
            else: 
                raise ValidationError(f"Encountered error saving status for order#{pk}")

            # Create ESCROW transaction
            transaction, _ = models.Transaction.objects.get_or_create(contract=contract, action=models.Transaction.ActionType.ESCROW)

            # Notify order WebSocket subscribers
            websocket_msg = {
                'success' : True,
                'status': status_serializer.data,
                'transaction': serializers.TransactionSerializer(transaction).data
            }
            websocket.send_order_update(websocket_msg, pk)
            response = websocket_msg
        except (ValidationError, IntegrityError, models.Contract.DoesNotExist) as err:
            return Response({'error': err.args[0]}, status=status.HTTP_400_BAD_REQUEST)

        return Response(response, status=status.HTTP_200_OK)

    @action(detail=True, methods=['post'])
    def verify_escrow(self, request, pk):
        '''
        Manually marks the order as ESCROWED by submitting the transaction id
        for validation (should only be used as fallback when listener fails to update the status 
        after calling ConfirmOrder).
        '''
        try:

            order = models.Order.objects.get(pk=pk)
            contract = models.Contract.objects.get(order_id=pk)

            # Check permissions
            self._check_escrow_permissions(request.user.wallet_hash, order)

            # Status validation
            validate_status(pk, StatusType.ESCROW_PENDING)
            validate_status_inst_count(StatusType.ESCROWED, pk)
            validate_status_progression(StatusType.ESCROWED, pk)

            txid = request.data.get('txid')
            if txid is None:
                raise ValidationError('txid is required')

            # Validate the transaction
            validate_transaction(txid, models.Transaction.ActionType.ESCROW, contract.id)

        except (ValidationError, models.Contract.DoesNotExist) as err:
            return Response({'error': err.args[0]}, status=status.HTTP_400_BAD_REQUEST)
        except IntegrityError as err:
            return Response({'error': 'duplicate txid'}, status=status.HTTP_400_BAD_REQUEST)
        
        return Response(status=status.HTTP_200_OK)  

    @action(detail=True, methods='post')
    def verify_release(self, request, pk):
        '''
        Manually marks the order as RELEASED by validating if a given transaction id (txid) 
        satisfies the requirements of its contract.
        Requirements:
            (1) Caller must be the order's arbiter or seller
            (2) The order's current status must be RELEASE_PENDING
        '''
        try:
            txid = request.data.get('txid')
            if txid is None:
                raise ValidationError('txid field is required')

            order = models.Order.objects.get(pk=pk)
            contract = models.Contract.objects.get(order__id=pk)

            # Check permissions
            self._check_release_permissions(request.user.wallet_hash, order)

            # Status validations
            status_type = StatusType.RELEASED
            validate_status_inst_count(status_type, pk)
            validate_exclusive_stats(status_type, pk)
            validate_status_progression(status_type, pk)      
            
            # Validate the transaction
            validate_transaction(txid, models.Transaction.ActionType.RELEASE, contract.id)
            
        except (ValidationError, models.Order.DoesNotExist, models.Contract.DoesNotExist, IntegrityError) as err:
            return Response({"success": False, "error": err.args[0]}, status=status.HTTP_400_BAD_REQUEST)
  
        return Response(status=status.HTTP_200_OK)

    @action(detail=True, methods='post')
    def verify_refund(self, request, pk):
        '''
        Manually marks the order as REFUNDED by validating if a given transaction id (txid) 
        satisfies the requirements of its contract.
        Requirements:
            (1) Caller must be the order's arbiter
            (2) The order's current status must be REFUND_PENDING
        '''
        try:
            txid = request.data.get('txid')
            if txid is None:
                raise ValidationError('txid field is required')
            
            order = models.Order.objects.get(pk=pk)
            contract = models.Contract.objects.get(order__id=pk)

            # Check permissions
            self._check_refund_permissions(request.user.wallet_hash, order)

            # Status validations
            status_type = StatusType.REFUNDED
            validate_status_inst_count(status_type, pk)
            validate_exclusive_stats(status_type, pk)
            validate_status_progression(status_type, pk)

            # Validate the transaction
            validate_transaction(txid, models.Transaction.ActionType.REFUND, contract.id)
            
        except (ValidationError, models.Order.DoesNotExist, models.Contract.DoesNotExist, IntegrityError) as err:
            return Response({"success": False, "error": err.args[0]}, status=status.HTTP_400_BAD_REQUEST)
  
        return Response(status=status.HTTP_200_OK)

    def _get_contract_params(self, arbiter, order):

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

    def _retrieve_transactions(self, contract_id):
        transactions = models.Transaction.objects.filter(contract__id=contract_id, txid__isnull=False)
        tx_data = []
        for _, tx in enumerate(transactions):
            tx_outputs = models.Recipient.objects.filter(transaction__id=tx.id)
            data = {}
            data["txn"] = serializers.TransactionSerializer(tx).data
            data["txn"]["outputs"] = serializers.RecipientSerializer(tx_outputs, many=True).data
            tx_data.append(data)
        return tx_data
    
    def _check_escrow_permissions(self, wallet_hash, order):
        '''Only sellers can verify the ESCROW status of order.'''
        if not order.is_seller(wallet_hash):
            raise ValidationError('Caller is not seller')

    def _check_release_permissions(self, wallet_hash, order):
        ''' Throws an error if (1) caller is the arbiter or seller and 
        (2) the order's current status is RELEASE_PENDING or PAID.
        '''
        # Check if user is arbiter or seller
        if not (order.is_arbiter(wallet_hash)) and not (order.is_seller(wallet_hash)):
            raise ValidationError('Caller is not seller nor arbiter')
        
        # Check if status is RELEASE_PENDING or PAID
        status = Status.objects.filter(order__id=order.id).latest('created_at')
        if not (status.status == StatusType.RELEASE_PENDING) and not (status.status == StatusType.PAID):
            raise ValidationError(f'Action requires status {StatusType.RELEASE_PENDING.label} or {StatusType.PAID.label}')

    def _check_refund_permissions(self, wallet_hash, order):
        '''Throws an error if user is not order's arbiter.'''
        if not order.is_arbiter(wallet_hash):
            raise ValidationError(f'Caller must be order arbiter.')
