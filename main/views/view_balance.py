from drf_yasg.utils import swagger_auto_schema
from main.models import Transaction, Wallet, Token
from django.db.models import Q, Sum, F
from django.db.models.functions import Coalesce
from rest_framework.response import Response
from rest_framework import status
from rest_framework.views import APIView
from main.utils.address_validator import *
from main.utils.address_converter import *
from main import serializers
from main.utils.tx_fee import (
    get_tx_fee_sats,
    bch_to_satoshi,
    satoshi_to_bch
)


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
    dust = 546 / (10 ** 8)
    query = query & Q(amount__gt=dust) & Q(token__name='bch')
    qs = Transaction.objects.filter(query)
    qs_count = qs.count()
    qs_balance = qs.aggregate(
        balance=Coalesce(Sum('amount'), 0)
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

    @swagger_auto_schema(responses={ 200: serializers.BalanceResponseSerializer })
    def get(self, request, *args, **kwargs):
        slpaddress = kwargs.get('slpaddress', '')
        bchaddress = kwargs.get('bchaddress', '')
        tokenaddress = kwargs.get('tokenaddress', '')
        tokenid = kwargs.get('tokenid', '')
        wallet_hash = kwargs.get('wallethash', '')

        data = { 'valid': False }
        balance = 0
        qs = None

        is_token_addr = is_token_address(tokenaddress)

        if is_slp_address(slpaddress) or is_token_addr:
            data['address'] = slpaddress
            if is_token_addr:
                data['address'] = bch_address_converter(tokenaddress, to_token_addr=False)

            if tokenid:
                multiple = False
                query = Q(address__address=data['address']) & Q(spent=False) & Q(token__tokenid=tokenid)
            else:
                multiple = True
                query = Q(address__address=data['address']) & Q(spent=False) & Q(token__is_cashtoken=is_token_addr)

            if is_token_addr:
                qs_balance = _get_ct_balance(query, multiple_tokens=multiple)
            else:
                qs_balance = _get_slp_balance(query, multiple_tokens=multiple)

            token = Token.objects.get(tokenid=tokenid)
            balance = qs_balance['amount__sum'] or 0

            if balance > 0 and token.decimals:
                balance = self.truncate(balance, token.decimals)
            data['balance'] = balance
            data['spendable'] = balance
            data['valid'] = True
        
        if is_bch_address(bchaddress):
            data['address'] = bchaddress
            query = Q(address__address=data['address']) & Q(spent=False)
            qs_balance, qs_count = _get_bch_balance(query)
            bch_balance = qs_balance['balance'] or 0

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
                if tokenid:
                    multiple = False
                    query = Q(wallet=wallet) & Q(spent=False) & Q(token__tokenid=tokenid)
                else:
                    multiple = True
                    query =  Q(wallet=wallet) & Q(spent=False)

                qs_balance = _get_slp_balance(query, multiple_tokens=multiple)

                if multiple:
                    pass
                else:
                    token = Token.objects.get(tokenid=tokenid)
                    balance = qs_balance['amount__sum'] or 0
                    if balance > 0 and token.decimals:
                        balance = self.truncate(balance, token.decimals)
                    data['balance'] = balance
                    data['spendable'] = balance
                    data['token_id'] = tokenid
                    data['valid'] = True

            elif wallet.wallet_type == 'bch':
                if tokenid:
                    multiple = False
                    query = Q(wallet=wallet) & Q(spent=False) & Q(token__tokenid=tokenid)
                    qs_balance = _get_ct_balance(query, multiple_tokens=multiple)
                else:
                    multiple = True
                    query = Q(wallet=wallet) & Q(spent=False) & Q(token__is_cashtoken=is_token_addr)
                
                if multiple:
                    if is_token_addr:
                        pass
                    else:
                        qs_balance, qs_count = _get_bch_balance(query)
                        bch_balance = qs_balance['balance']

                        data['spendable'] = int(bch_to_satoshi(bch_balance)) - get_tx_fee_sats(p2pkh_input_count=qs_count)
                        data['spendable'] = satoshi_to_bch(data['spendable'])
                        data['spendable'] = max(data['spendable'], 0)
                        data['spendable'] = self.truncate(data['spendable'], 8)

                        data['balance'] = self.truncate(qs_balance['balance'], 8)
                        data['valid'] = True
                else:
                    token = Token.objects.get(tokenid=tokenid)
                    balance = qs_balance['amount__sum'] or 0
                    if balance > 0 and token.decimals:
                        balance = self.truncate(balance, token.decimals)
                    data['balance'] = balance
                    data['spendable'] = balance
                    data['token_id'] = tokenid
                    data['valid'] = True

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
        bch_balance = qs_balance
        qs_balance = round(qs_balance, 8)

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

        data['balance'] = qs_balance

        return Response(data, status=200)
