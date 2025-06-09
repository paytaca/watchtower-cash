import json
import math
import decimal
from django.utils import timezone
from django.conf import settings
from django.db.models import Sum, Count, F, Q
from django.db.models import DecimalField

from stablehedge.apps import LOGGER
from stablehedge import models
from stablehedge.js.runner import ScriptFunctions
from stablehedge.exceptions import StablehedgeException
from stablehedge.utils.anyhedge import get_latest_oracle_price
from stablehedge.utils.wallet import wif_to_cash_address, is_valid_wif, get_bch_transaction_objects
from stablehedge.utils.transaction import tx_model_to_cashscript, utxo_data_to_cashscript, validate_utxo_data, InvalidUtxoException

from main import models as main_models

from .treasury_contract import get_funding_wif


REDIS_STORAGE = settings.REDISKV

def find_fiat_token_utxos(redemptionContractOrAddress, min_token_amount=None, min_satoshis=None):
    if isinstance(redemptionContractOrAddress, str):
        obj = models.RedemptionContract.objects.get(address=redemptionContractOrAddress)
    else:
        obj = redemptionContractOrAddress

    token_category = obj.fiat_token.category
    queryset = main_models.Transaction.objects.filter(
        address__address=obj.address,
        cashtoken_ft__category=token_category,
        spent=False,
    )

    if min_token_amount is not None:
        queryset = queryset.filter(amount__gte=min_token_amount)
    if min_satoshis is not None:
        queryset = queryset.filter(value__gte=min_satoshis)

    return queryset


def get_fiat_token_balances(wallet_hash:str, with_satoshis=False):
    redemption_contract_data_qs = models.RedemptionContract.objects \
        .values("fiat_token__category", "fiat_token__decimals", "fiat_token__currency", "price_oracle_pubkey") \
        .distinct()

    token_oracle_map = {}
    token_decimals_map = {}
    token_currency_map = {}
    for redemption_contract_data in redemption_contract_data_qs:
        token_category = redemption_contract_data["fiat_token__category"]
        oracle_pubkey = redemption_contract_data["price_oracle_pubkey"]
        decimals = redemption_contract_data["fiat_token__decimals"]
        currency = redemption_contract_data["fiat_token__currency"]
        token_oracle_map[token_category] = oracle_pubkey
        token_decimals_map[token_category] = decimals
        token_currency_map[token_category] = currency


    fiat_token_categories = list(token_oracle_map.keys())

    token_balances = main_models.Transaction.objects \
        .filter(cashtoken_ft__category__in=fiat_token_categories) \
        .filter(wallet__wallet_hash=wallet_hash) \
        .filter(spent=False) \
        .annotate(category=F("cashtoken_ft__category")) \
        .values("category") \
        .order_by("category") \
        .annotate(total_amount = Sum("amount")) \
        .values("category", "total_amount")

    for data in token_balances:
        data["currency"] = token_currency_map.get(data["category"])

    if not with_satoshis:
        return token_balances

    for data in token_balances:
        oracle_pubkey = token_oracle_map.get(data["category"])
        decimals = token_decimals_map.get(data["category"]) or 0

        if not oracle_pubkey:
            continue

        latest_price = get_latest_oracle_price(oracle_pubkey)

        if not latest_price:
            continue

        redeemable = data["total_amount"] / latest_price
        redeemable = math.floor(redeemable)

        data["current_price"] = latest_price
        data["redeemable_satoshis"] = redeemable 

    return token_balances

def get_24hr_volume_data(redemption_contract_address:str, ttl=60 * 5, force=False):
    return get_volume_data(
        redemption_contract_address,
        filter_args=[Q(created_at__gte=timezone.now() - timezone.timedelta(seconds=86_400))],
        cache_key="24hr", ttl=ttl, force=force,
    )

def get_lifetime_volume_data(redemption_contract_address:str, ttl=60*5, force=False):
    return get_volume_data(
        redemption_contract_address, filter_args=[],
        cache_key="lifetime", ttl=ttl, force=force,
    )

def get_volume_data(
    redemption_contract_address:str,
    filter_args:list=[],
    cache_key:str="",
    ttl:int=60*5,
    force=False,
):
    REDIS_KEY = f"redemption-contract-volume:{redemption_contract_address}:{cache_key}"

    if not force:
        cached_value = REDIS_STORAGE.get(REDIS_KEY)
        if cached_value:
            LOGGER.debug(f"Cached volume data | {REDIS_KEY} | {cached_value}")
            try:
                data = json.loads(cached_value)
                for index, record in enumerate(data):
                    data[index]["satoshis"] = decimal.Decimal(record["satoshis"])
                    data[index]["count"] = int(record["count"])
                return data
            except (TypeError, AttributeError, decimal.InvalidOperation) as exception:
                LOGGER.exception(exception)

    data = models.RedemptionContractTransaction.objects \
        .filter(
            *filter_args,
            redemption_contract__address=redemption_contract_address,
            status=models.RedemptionContractTransaction.Status.SUCCESS,
            txid__isnull=False,
        ) \
        .values("transaction_type") \
        .annotate(
            satoshis=Sum(
                "trade_size_in_satoshis",
                output_field=DecimalField(max_digits=15, decimal_places=0)
            ),
            count=Count("id"),
        ) \
        .values("transaction_type", "satoshis", "count").distinct()

    parsed_data = [*data]
    REDIS_STORAGE.set(REDIS_KEY, str(json.dumps(parsed_data, default=str)), ex=ttl)
    return parsed_data


def get_redemption_contract_bch_utxos(redemption_contract_address:str, satoshis:int=None):
    return get_bch_transaction_objects(
        redemption_contract_address,
        satoshis=satoshis,
        fee_sats_per_input=400,
    )


def get_funding_utxo_for_consolidation(redemption_contract_address:str, wif:str, utxos_count:int):
    redemption_contract = models.RedemptionContract.objects \
        .filter(address=redemption_contract_address) \
        .first()

    if not redemption_contract:
        raise StablehedgeException("Redemption contract not found", code="contract_not_found")

    if not wif and redemption_contract.treasury_contract:
        wif = get_funding_wif(redemption_contract.treasury_contract.address)

    if not wif:
        raise StablehedgeException("Funding WIF not set", code="funding_wif_not_set")
    
    if not is_valid_wif(wif):
        raise StablehedgeException("Invalid funding WIF", code="invalid_funding_wif")

    address = wif_to_cash_address(wif, testnet=settings.BCH_NETWORK == "chipnet")
    return wif, main_models.Transaction.objects.filter(
        address__address=address,
        token__name="bch",
        spent=False,
        value__gte=1000 + utxos_count * 400,
    ).first()

def consolidate_redemption_contract(
    redemption_contract_address:str,
    with_reserve_utxo:bool=True,
    funding_wif:str=None,
    locktime:int=0,
    manual_utxos:list=[],
    append_manual_utxos:bool=False,
    funding_utxo_data:dict=None,
):
    redemption_contract = models.RedemptionContract.objects \
        .filter(address=redemption_contract_address) \
        .first()

    if not redemption_contract:
        raise StablehedgeException("Redemption contract not found", code="contract_not_found")

    if len(manual_utxos):
        valid_utxos = [validate_utxo_data(utxo, raise_error=False) for utxo in manual_utxos]
        if not all(valid_utxos):
            raise StablehedgeException("Invalid manual UTXOs", code="invalid_manual_utxos")
        manual_utxos = [utxo_data_to_cashscript(utxo) for utxo in manual_utxos]

    # len(manual_utxos) or append_manual_utxos
    # 0 0 => 1
    # 0 1 => 1
    # 1 0 => 0
    # 1 1 => 1
    # get utxos
    if not len(manual_utxos) or append_manual_utxos:
        utxos = get_redemption_contract_bch_utxos(redemption_contract_address)
        if not len(utxos) and (not append_manual_utxos or not len(manual_utxos)):
            raise StablehedgeException("No UTXOs found", code="no_utxos")

        if with_reserve_utxo:
            reserve_utxo = find_fiat_token_utxos(redemption_contract).first()
            utxos = [reserve_utxo, *utxos]

        cashscript_utxos = [tx_model_to_cashscript(utxo) for utxo in utxos]

        if append_manual_utxos:
            cashscript_utxos = [*cashscript_utxos, *manual_utxos]
    else:
        cashscript_utxos = manual_utxos

    if funding_utxo_data is not None:
        try:
            validate_utxo_data(funding_utxo_data, require_unlock="wif" not in funding_utxo_data)
            funding_utxo_data = utxo_data_to_cashscript(funding_utxo_data)
        except InvalidUtxoException as exception:
            raise StablehedgeException(
                f"Invalid funding UTXO data: {str(exception)}",
                code="invalid_funding_utxo_data"
            )

    else:
        fee_funder_wif, funding_utxo = get_funding_utxo_for_consolidation(
            redemption_contract.address, funding_wif, len(cashscript_utxos),
        )
        if not funding_utxo:
            raise StablehedgeException("Funding UTXO not found", code="funding_utxo_not_found")

        funding_utxo_data = tx_model_to_cashscript(funding_utxo)
        funding_utxo_data["wif"] = fee_funder_wif

    # create transaction
    result = ScriptFunctions.consolidateRedemptionContract(dict(
        contractOpts=redemption_contract.contract_opts,
        locktime=locktime,
        feeFunderUtxo=funding_utxo_data,
        inputs=cashscript_utxos,
        # satoshis=satoshis,
    ))

    if "success" not in result or not result["success"]:
        raise StablehedgeException(result.get("error", "Unknown error"))

    return result["tx_hex"]
