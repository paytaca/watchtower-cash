
from stablehedge import models

from main import models as main_models

def find_fiat_token_utxos(redemptionContractOrAddress, min_token_amount=None, min_satoshis=None):
    if isinstance(redemptionContractOrAddress, str):
        obj = models.RedemptionContract(redemptionContractOrAddress)
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
