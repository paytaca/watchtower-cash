from main.models import Transaction, WalletHistory, Address, Wallet, Recipient, Subscription
from paytacapos.models import PayoutAddress
from django.db.models import Q, Func, Subquery
from django.conf import settings
from main.serializers import SubscriberSerializer
from main.utils.subscription import new_subscription

import bip32utils
import cashaddress
import logging

logger = logging.getLogger(__name__)

def fetch_unspent_merchant_transactions(wallet_hash, posids):
    """
    Find unspent, incoming transactions by wallet_hash and posids.
    """

    if len(posids) == 0:
        return []

    # Filter unspent transactions by wallet_hash
    unspent_txns = Transaction.objects.filter(wallet__wallet_hash=wallet_hash, spent=False)
    unspent_txids = unspent_txns.values_list('txid', flat=True)

    # Filter incoming unspent WalletHistory transactions by txid
    incoming_unspent_txns = WalletHistory.objects.filter(
        txid__in=unspent_txids,
        record_type=WalletHistory.INCOMING,
        wallet__wallet_hash=wallet_hash,
        token__name="bch")

    # Transform posids into regex patterns
    transformed_posids = [f"((0|1)/)?0*\d+{posid}" for posid in posids]

    # Create a Q object for posid regex filtering
    posid_regex_query = Q()
    for regex in transformed_posids: 
        posid_regex_query |= Q(address_path__iregex=regex)

    # Filter addresses based on wallet_hash and posid regex
    address_queryset = Address.objects.filter(wallet__wallet_hash=wallet_hash).filter(posid_regex_query).values('address').distinct()

    # Extract posid-filtered addresses into a list
    pos_addresses = address_queryset.values('address').distinct()
    pos_addresses_subquery = Func(Subquery(pos_addresses), function="array")

    # Filter WalletHistory transactions where recipients overlap with posid-filtered addresses
    unspent_merchant_txns = incoming_unspent_txns.filter(recipients__overlap=pos_addresses_subquery)
    
    return unspent_merchant_txns

def save_and_subsribe_to_address(data, index):

    # save as PayoutAddress
    PayoutAddress.objects.get_or_create(address=data['address'], index=index)

    # subscribe
    serializer = SubscriberSerializer(data=data)
    if serializer.is_valid():
        response = new_subscription(**serializer.data)

    return response

def generate_address_from_xpubkey(xpubkey):
    if not xpubkey:
        raise Exception('paytacapos payout xpubkey not set')
        
    key = bip32utils.BIP32Key.fromExtendedKey(xpubkey, public=True)
    last_payout_address = PayoutAddress.objects.last()
    
    next_index = 0
    if last_payout_address:
        last_index = last_payout_address.index or 0
        next_index = last_index + 1

    bch_legacy_address = key.ChildKey(next_index).Address()
    address = cashaddress.convert.to_cash_address(bch_legacy_address)
    return address, next_index

def generate_payout_address(fixed=True):

    payout_address = settings.PAYTACAPOS_PAYOUT_ADDRESS
    wallet_hash = settings.PAYTACAPOS_PAYOUT_WALLET_HASH

    if not wallet_hash:
        raise Exception('paytacapos payout wallet_hash not set')
    
    next_index = None
    if not fixed:
        payout_address, next_index = generate_address_from_xpubkey(settings.PAYTACAPOS_PAYOUT_XPUBKEY)
    
    save_and_subsribe_to_address({ 'address': payout_address, 'wallet_hash': wallet_hash }, next_index)

    return payout_address

