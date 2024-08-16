from django.conf import settings
from drf_yasg.utils import swagger_auto_schema
from main.models import Transaction, Wallet, Token, CashFungibleToken, CashNonFungibleToken
from django.db.models import Q, Sum, F
from django.utils import timezone
from django.db.models.functions import Coalesce
from rest_framework.response import Response
from rest_framework import status
from rest_framework.views import APIView
from main.utils.address_validator import *
from main.utils.address_converter import *
from main.utils.bch_yield import compute_wallet_yield
from main import serializers
from main.tasks import rescan_utxos
from main.utils.tx_fee import (
    get_tx_fee_sats,
    bch_to_satoshi,
    satoshi_to_bch
)

import logging
LOGGER = logging.getLogger(__name__)


def _get_slp_balance(query, multiple_tokens=False):
    qs = Transaction.objects.filter(query)
    if multiple_tokens:
        # TODO: This is not working as expected in PostgresModel manager
        # I created a github issue for this here:
        # https://github.com/SectorLabs/django-postgres-extra/issues/143
        # Multiple tokens balance will be disabled til that issue is resolved
        qs_balance = qs.annotate(
            _token=F('token__tokenid'),
            token_name=F('token__name'),
            token_ticker=F('token__token_ticker'),
            token_type=F('token__token_type')
        ).rename_annotations(
            _token='token_id'
        ).values(
            'token_id',
            'token_name',
            'token_ticker',
            'token_type'
        ).annotate(
            balance=Coalesce(Sum('amount'), 0)
        )
    else:
        qs_balance = qs.aggregate(Sum('amount'))
    return qs_balance


def _get_ct_balance(query, multiple_tokens=False):
    return _get_slp_balance(query, multiple_tokens)


def _get_bch_balance(query):
    # Exclude dust amounts as they're likely to be SLP transactions
    # TODO: Needs another more sure way to exclude SLP transactions
    dust = 546 # / (10 ** 8)
    query = query & Q(value__gt=dust) & Q(token__name='bch')
    qs = Transaction.objects.filter(query)
    qs_count = qs.count()
    qs_balance = qs.aggregate(
        balance=Coalesce(Sum('value'), 0)
    )
    return qs_balance, qs_count

class Balance(APIView):

    def truncate(self, num, decimals):
        """
        Truncate instead of rounding off
        Rounding off sometimes results to a value greater than the actual balance
        """
        # Preformat first if it it's in scientific notation form
        if 'e-' in str(num):
            num, power = str(num).split('e-')
            power = int(power)
            num = num.replace('.', '')
            left_pad = (power - 1) * '0'
            sp = '0.' + left_pad + num
        else:
            sp = str(num)
        # Proceed to truncate
        sp = sp.split('.')
        if len(sp) == 2:
            return float('.'.join([sp[0], sp[1][:decimals]]))
        else:
            return num

    def get(self, request, *args, **kwargs):
        slpaddress = kwargs.get('slpaddress', '')
        bchaddress = kwargs.get('bchaddress', '')
        tokenaddress = kwargs.get('tokenaddress', '')
        tokenid = kwargs.get('tokenid', '')
        category = kwargs.get('category', '')
        index = kwargs.get('index', '')
        txid = kwargs.get('txid', '')
        tokenid_or_category = kwargs.get('tokenid_or_category', '')
        wallet_hash = kwargs.get('wallethash', '')

        is_cashtoken_nft = False
        if index and txid:
            index = int(index)
            is_cashtoken_nft = True

        data = { 'valid': False }
        balance = 0
        qs = None

        is_token_addr = is_token_address(tokenaddress)

        if is_slp_address(slpaddress) or is_token_addr:
            data['address'] = slpaddress
            if is_token_addr:
                data['address'] = bch_address_converter(tokenaddress, to_token_addr=False)

            if tokenid or category:
                multiple = False
                if is_token_addr:
                    query = Q(address__address=data['address']) & Q(spent=False)

                    if is_cashtoken_nft:
                        query = (
                            query &
                            Q(cashtoken_nft__category=category) &
                            Q(cashtoken_nft__current_index=index) &
                            Q(cashtoken_nft__current_txid=txid)
                        )
                    else:
                        query = query & Q(cashtoken_ft__category=category)
                else:
                    query = Q(address__address=data['address']) & Q(spent=False) & Q(token__tokenid=tokenid)
            else:
                multiple = True
                if is_token_addr:
                    query = Q(address__address=data['address']) & Q(spent=False) & Q(token__tokenid=settings.WT_DEFAULT_CASHTOKEN_ID)
                else:
                    query = Q(address__address=data['address']) & Q(spent=False)

            if is_token_addr:
                qs_balance = _get_ct_balance(query, multiple_tokens=multiple)
            else:
                qs_balance = _get_slp_balance(query, multiple_tokens=multiple)

            if is_token_addr:
                if is_cashtoken_nft:
                    token = CashNonFungibleToken.objects.get(
                        category=category,
                        current_index=index,
                        current_txid=txid
                    )
                else:
                    token = CashFungibleToken.objects.get(category=category)
                
                decimals = 0
                if token.info:
                    decimals = token.info.decimals
            else:
                token = Token.objects.get(tokenid=tokenid)
                decimals = token.decimals
            
            balance = qs_balance['amount__sum'] or 0
            if balance > 0:
                balance = self.truncate(balance, decimals)

            data['balance'] = balance
            data['spendable'] = balance
            data['valid'] = True

            if is_cashtoken_nft:
                data['commitment'] = token.commitment
                data['capability'] = token.capability
        
        if is_bch_address(bchaddress):
            data['address'] = bchaddress
            query = Q(address__address=data['address']) & Q(spent=False)
            qs_balance, qs_count = _get_bch_balance(query)
            bch_balance = qs_balance['balance'] or 0
            bch_balance = bch_balance / (10 ** 8)

            data['spendable'] = int(bch_to_satoshi(bch_balance)) - get_tx_fee_sats(p2pkh_input_count=qs_count)
            data['spendable'] = satoshi_to_bch(data['spendable'])
            data['spendable'] = max(data['spendable'], 0)
            data['spendable'] = self.truncate(data['spendable'], 8)

            data['balance'] = self.truncate(bch_balance, 8)
            data['valid'] = True

        if wallet_hash:
            wallet = Wallet.objects.get(wallet_hash=wallet_hash)
            data['wallet'] = wallet_hash

            if wallet.wallet_type == 'slp':
                if tokenid_or_category:
                    multiple = False
                    query = Q(wallet=wallet) & Q(spent=False) & Q(token__tokenid=tokenid_or_category)
                else:
                    multiple = True
                    query =  Q(wallet=wallet) & Q(spent=False)

                qs_balance = _get_slp_balance(query, multiple_tokens=multiple)

                if multiple:
                    pass
                else:
                    token = Token.objects.get(tokenid=tokenid_or_category)
                    balance = qs_balance['amount__sum'] or 0
                    if balance > 0 and token.decimals:
                        balance = self.truncate(balance, token.decimals)
                    data['balance'] = balance
                    data['spendable'] = balance
                    data['token_id'] = tokenid_or_category
                    data['valid'] = True

            elif wallet.wallet_type == 'bch':
                
                # Execute UTXO scanning if conditions are met
                execute_utxo_scan = False
                if wallet.last_balance_check:
                    # Trigger scan if last balance check is more than an hour ago
                    time_diff = timezone.now() - wallet.last_balance_check
                    if time_diff.total_seconds() > 3600:
                        execute_utxo_scan = True
                else:
                    # Trigger scan if last_balance_check is none
                    execute_utxo_scan = True
                if execute_utxo_scan:
                    rescan_utxos.delay(wallet_hash, full=True)

                if tokenid_or_category or category:
                    is_bch = False
                    query = Q(wallet=wallet) & Q(spent=False)

                    if is_cashtoken_nft:
                        query = (
                            query &
                            Q(cashtoken_nft__category=category) &
                            Q(cashtoken_nft__current_index=index) &
                            Q(cashtoken_nft__current_txid=txid)
                        )
                    else:
                        query = query & Q(cashtoken_ft__category=tokenid_or_category)

                    qs_balance = _get_ct_balance(query, multiple_tokens=False)
                else:
                    is_bch = True
                    query = Q(wallet=wallet) & Q(spent=False)
                
                if is_bch:
                    qs_balance, qs_count = _get_bch_balance(query)
                    bch_balance = qs_balance['balance'] or 0
                    bch_balance = bch_balance / (10 ** 8)

                    data['spendable'] = int(bch_to_satoshi(bch_balance)) - get_tx_fee_sats(p2pkh_input_count=qs_count)
                    data['spendable'] = satoshi_to_bch(data['spendable'])
                    data['spendable'] = max(data['spendable'], 0)
                    data['spendable'] = self.truncate(data['spendable'], 8)

                    data['balance'] = self.truncate(bch_balance, 8)
                    data['yield'] = None # compute_wallet_yield(wallet_hash)
                    data['valid'] = True
                else:
                    if is_cashtoken_nft:
                        token = CashNonFungibleToken.objects.get(
                            category=category,
                            current_index=index,
                            current_txid=txid
                        )
                    else:
                        token = CashFungibleToken.objects.get(category=tokenid_or_category)

                    balance = qs_balance['amount__sum'] or 0
                    decimals = 0
                    if token.info:
                        decimals = token.info.decimals

                    if balance > 0:
                        balance = self.truncate(balance, decimals)

                    data['balance'] = balance
                    data['spendable'] = balance
                    data['token_id'] = tokenid_or_category or category
                    data['valid'] = True
                    
                    if is_cashtoken_nft:
                        data['commitment'] = token.commitment
                        data['capability'] = token.capability

            # Update last_balance_check timestamp
            wallet.last_balance_check = timezone.now()
            wallet.save()

        return Response(data=data, status=status.HTTP_200_OK)


class SpendableBalance(APIView):
    @swagger_auto_schema(
        request_body=serializers.TxFeeCalculatorSerializer,
        responses={ 200: serializers.BalanceResponseSerializer },
    )
    def post(self, request, *args, **kwargs):
        bchaddress = kwargs.get('bchaddress', '')
        wallet_hash = kwargs.get('wallethash', '')

        data = {
            'valid': True,
        }

        qs_balance = 0
        qs_count = 0
        if is_bch_address(bchaddress):
            data['address'] = bchaddress
            query = Q(address__address=bchaddress) & Q(spent=False)
            qs_balance, qs_count = _get_bch_balance(query)
        elif wallet_hash:
            wallet = Wallet.objects.get(wallet_hash=wallet_hash)
            data['wallet'] = wallet_hash
            if wallet.wallet_type != 'bch':
                return Response({ 'detail': 'Invalid wallet type' }, status=400)

            query = Q(wallet=wallet) & Q(spent=False)
            qs_balance, qs_count = _get_bch_balance(query)

        qs_balance = qs_balance['balance'] or 0
        bch_balance = qs_balance / (10 ** 8)
        bch_balance = round(bch_balance, 8)

        serializer = serializers.TxFeeCalculatorSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        tx_fee_kwargs = serializer.validated_data

        if not isinstance(tx_fee_kwargs.get('p2pkh_input_count', None), int):
            tx_fee_kwargs['p2pkh_input_count'] = 0

        tx_fee_kwargs['p2pkh_input_count'] += qs_count
        tx_fee = get_tx_fee_sats(**tx_fee_kwargs)

        data['spendable'] = int(bch_to_satoshi(bch_balance)) - round(tx_fee)
        data['spendable'] = satoshi_to_bch(data['spendable'])
        data['spendable'] = max(data['spendable'], 0)

        data['balance'] = bch_balance

        return Response(data, status=200)
