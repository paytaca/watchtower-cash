from drf_yasg import openapi
from drf_yasg.utils import swagger_auto_schema
from django.db.models import Q, F, Func, OuterRef, Exists, CharField, IntegerField
from django.db.models.functions import Cast
from django.contrib.postgres.fields.jsonb import KeyTextTransform
from django.contrib.postgres.fields import JSONField
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from drf_yasg import openapi
from drf_yasg.utils import swagger_auto_schema

from main.models import Transaction, Wallet, Token
from main.tasks import rescan_utxos
from main.throttles import ScanUtxoThrottle
from main.utils.address_validator import *
from main.utils.address_converter import *


class Round(Func):
    function = "ROUND"
    template = "%(function)s(%(expressions)s::numeric, 0)"


def _get_slp_utxos(query, show_address_index=False, minting_baton=None):
    qs = Transaction.objects.filter(query)
    if minting_baton is not None:
        subquery = Exists(
            Token.objects.annotate(
                minting_baton=Cast(KeyTextTransform('minting_baton', 'nft_token_group_details'), JSONField()),
            ).annotate(
                minting_baton_txid=Cast(KeyTextTransform('txid', 'minting_baton'), CharField()),
                minting_baton_index=Cast(KeyTextTransform('index', 'minting_baton'), IntegerField()),
            ).filter(
                minting_baton_txid=OuterRef("txid"),
                minting_baton_index=OuterRef("index"),
            ).values('tokenid')
        )
        if minting_baton:
            qs = qs.filter(subquery)
        else:
            qs = qs.exclude(subquery)

    if show_address_index:
        utxos_values = qs.annotate(
            vout=F('index'),
            tokenid=F('token__tokenid'),
            token_name=F('token__name'),
            decimals=F('token__decimals'),
            token_ticker=F('token__token_ticker'),
            token_type=F('token__token_type'),
            block=F('blockheight__number'),
            wallet_index=F('address__wallet_index'),
            address_path=F('address__address_path'),
            is_cashtoken=F('token__is_cashtoken')
        ).values(
            'txid',
            'vout',
            'amount',
            'tokenid',
            'token_name',
            'token_ticker',
            'decimals',
            'token_type',
            'block',
            'wallet_index',
            'address_path',
            'is_cashtoken'
        )
    else:
        utxos_values = qs.annotate(
            vout=F('index'),
            tokenid=F('token__tokenid'),
            token_name=F('token__name'),
            decimals=F('token__decimals'),
            token_ticker=F('token__token_ticker'),
            token_type=F('token__token_type'),
            block=F('blockheight__number'),
            is_cashtoken=F('token__is_cashtoken')
        ).values(
            'txid',
            'vout',
            'amount',
            'tokenid',
            'token_name',
            'token_ticker',
            'decimals',
            'token_type',
            'block',
            'is_cashtoken'
        )
    return utxos_values


def _get_ct_utxos(query, show_address_index=False):
    return _get_slp_utxos(query, show_address_index=show_address_index)


def _get_bch_utxos(query, show_address_index=False):
    # Exclude dust amounts as they're likely to be SLP transactions
    # TODO: Needs another more sure way to exclude SLP transactions
    dust = 546 / (10 ** 8)
    query = query & Q(amount__gt=dust) & Q(token__name='bch')
    qs = Transaction.objects.filter(query)
    if show_address_index:
        utxos_values = qs.annotate(
            value=Round(F('amount') * (10 ** 8)),
            vout=F('index'),
            block=F('blockheight__number'),
            wallet_index=F('address__wallet_index'),
            address_path=F('address__address_path')
        ).values(
            'txid',
            'vout',
            'value',
            'block',
            'wallet_index',
            'address_path'
        )
    else:
        utxos_values = qs.annotate(
            value=Round(F('amount') * (10 ** 8)),
            vout=F('index'),
            block=F('blockheight__number'),
        ).values(
            'txid',
            'vout',
            'value',
            'block'
        )
    return utxos_values


class UTXO(APIView):

    @swagger_auto_schema(
        manual_parameters=[
            openapi.Parameter(name="baton", type=openapi.TYPE_BOOLEAN, in_=openapi.IN_QUERY, required=False),
        ]
    )
    def get(self, request, *args, **kwargs):
        slpaddress = kwargs.get('slpaddress', '')
        bchaddress = kwargs.get('bchaddress', '')
        tokenaddress = kwargs.get('tokenaddress', '')
        tokenid = kwargs.get('tokenid', '')
        wallet_hash = kwargs.get('wallethash', '')
        baton = request.query_params.get('baton', '').lower().strip()
        if baton == "true":
            baton = True
        elif baton == "false":
            baton = False
        else:
            baton = None

        data = { 'valid': False }
        qs = None

        is_token_addr = is_token_address(tokenaddress)
        
        if is_bch_address(bchaddress):
            data['address'] = bchaddress
            query = Q(address__address=data['address']) & Q(spent=False)
            utxos_values = _get_bch_utxos(query)
        
        if is_slp_address(slpaddress) or is_token_addr:
            data['address'] = slpaddress
            if is_token_addr:
                data['address'] = bch_address_converter(tokenaddress, to_token_addr=False)

            if tokenid:
                query = Q(address__address=data['address']) & Q(spent=False) & Q(token__tokenid=tokenid)
            else:
                query = Q(address__address=data['address']) & Q(spent=False) & Q(token__is_cashtoken=is_token_addr)

            if is_token_addr:
                utxos_values = _get_ct_utxos(query)
            else:
                utxos_values = _get_slp_utxos(query, minting_baton=baton)

        if wallet_hash:
            wallet = Wallet.objects.get(wallet_hash=wallet_hash)
            data['wallet'] = wallet_hash
            
            if wallet.wallet_type == 'slp':
                if tokenid:
                    query = Q(wallet=wallet) & Q(spent=False) & Q(token__tokenid=tokenid)
                else:
                    query = Q(wallet=wallet) & Q(spent=False)

                utxos_values = _get_slp_utxos(query, show_address_index=True, minting_baton=baton)

            elif wallet.wallet_type == 'bch':
                if tokenid:
                    query = Q(wallet=wallet) & Q(spent=False) & Q(token__tokenid=tokenid)
                    utxos_values = _get_ct_utxos(query, show_address_index=True)
                else:
                    query = Q(wallet=wallet) & Q(spent=False)
                    utxos_values = _get_bch_utxos(query, show_address_index=True)

        if baton is not None:
            data['minting_baton'] = baton

        data['utxos'] = list(utxos_values)
        data['valid'] = True  
        return Response(data=data, status=status.HTTP_200_OK)


class ScanUtxos(APIView):
    throttle_classes = [ScanUtxoThrottle]

    @swagger_auto_schema(
        manual_parameters=[
            openapi.Parameter(name="background", type=openapi.TYPE_BOOLEAN, in_=openapi.IN_QUERY, default=False),
        ]
    )
    def get(self, request, *args, **kwargs):
        wallet_hash = kwargs.get('wallethash', '')
        background = request.query_params.get("background", None)
        if isinstance(background, str) and background.lower() == "false":
            background = False

        try:
            wallet = Wallet.objects.get(wallet_hash=wallet_hash)
        except Wallet.DoesNotExist:
            return Response(status=status.HTTP_404_NOT_FOUND)

        if background:
            task = rescan_utxos.delay(wallet.wallet_hash, full=True)
            return Response({ "task_id": task.id }, status = status.HTTP_202_ACCEPTED)

        rescan_utxos(wallet.wallet_hash, full=True)
        return Response(data={'success': True}, status=status.HTTP_200_OK)
