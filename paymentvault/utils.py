from rest_framework import serializers
from django.conf import settings

from paytacapos.models import Merchant
from .models import *

import requests
import logging

logger = logging.getLogger(__name__)


def get_payment_vault(user_pubkey, merchant_pubkey):
    url = settings.VAULT_EXPRESS_URL
    url += f'/{user_pubkey}/{merchant_pubkey}'
    url += f'?network={settings.BCH_NETWORK}'
    response = requests.get(url)
    response = response.json()
    return response


def create_vault(user_pubkey, merchant):
    vault = get_payment_vault(user_pubkey, merchant.pubkey)
    contract = vault['contract']
    
    payment_vault = PaymentVault.objects.create(
        user_pubkey=user_pubkey,
        merchant=merchant,
        address=contract['address'],
        token_address=contract['tokenAddress']
    )
    return payment_vault