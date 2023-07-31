from django.db.models import OuterRef, Exists
from paytacapos.models import (
    Merchant, 
    PosDevice,
)

# Will be used for the marketplace update in PaytacaPOS app where;
# a pos device must belong to a branch to enable marketplace
def populate_pos_device_branches():
    has_devices_without_branch = Exists(
        PosDevice.objects.filter(wallet_hash=OuterRef("wallet_hash"), branch__isnull=True)
    )
    merchants = Merchant.objects.filter(has_devices_without_branch).all()
    results = []
    for merchant in merchants:
        main_branch, _ = merchant.get_or_create_main_branch()
        response = PosDevice.objects \
            .filter(wallet_hash=merchant.wallet_hash) \
            .filter(branch__isnull=True) \
            .update(branch=main_branch)

        result = (merchant, response)
        results.append(result)
    return results
