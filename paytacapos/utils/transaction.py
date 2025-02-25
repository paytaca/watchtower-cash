from main.models import Transaction, WalletHistory, Address
from django.db.models import Q, Func, Subquery
import logging

logger = logging.getLogger(__name__)

def fetch_unspent_merchant_transactions(wallet_hash, posids):
    """
    Find unspent, incoming transactions by wallet_hash and posids.
    """

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