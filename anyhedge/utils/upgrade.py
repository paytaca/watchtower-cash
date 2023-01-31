"""
    Some functions to run for syncing data into new fields created from the upgrade
    Recommended to run after deploying but should work even without running them
"""
from django.db import models
from anyhedge.models import (
    HedgePosition,
    HedgePositionFunding,
    HedgeSettlement,
    HedgePositionOffer,
    HedgePositionOfferCounterParty,
    PriceOracleMessage,
)

def run_sync_functions():
    return {
        "hedge_position_oracle_messages_updated": set_hedge_position_starting_oracle_messages(),
        "hedge_position_offer_oracle_message_updated": set_hedge_position_offer_starting_oracle_messages(),
        "fundings_synced": sync_fundings(),
        "settlements_synced": sync_settlements(),
    }

def set_hedge_position_starting_oracle_messages():
    message_subquery = models.Subquery(
        PriceOracleMessage.objects.filter(
            pubkey=models.OuterRef("oracle_pubkey"),
            message_timestamp=models.OuterRef("start_timestamp"),
        ).values("message")[:1]
    )
    signature_subquery = models.Subquery(
        PriceOracleMessage.objects.filter(
            pubkey=models.OuterRef("oracle_pubkey"),
            message_timestamp=models.OuterRef("start_timestamp"),
        ).values("signature")[:1]
    )

    return HedgePosition.objects.filter(
        models.Q(starting_oracle_message="") | models.Q(starting_oracle_signature="")
    ).update(
        starting_oracle_message=message_subquery,
        starting_oracle_signature=signature_subquery,
    )

def sync_fundings():
    hedge_position_id_subquery = models.Subquery(
        HedgePosition.objects.filter(
            funding_tx_hash=models.OuterRef("tx_hash"),
        ).values("id")[:1]
    )

    return HedgePositionFunding.objects.filter(
        hedge_position__isnull=True,
    ).update(
        hedge_position_id=hedge_position_id_subquery,
        validated=True,
    )

def sync_settlements():
    """
        This assumes that 'sync_fundings' was run
        Only affects hedge positions with only 1 HedgePositionFunding and HedgeSettlement
        since having more than one requires matching the settlement tx's input which is not 
        available in db
    """
    settlement_id_subquery = models.Subquery(
        HedgeSettlement.objects.filter(
            hedge_position=models.OuterRef("hedge_position"),
        ).values("id")[:1]
    )

    return HedgePositionFunding.objects.annotate(
        hedge_position_fundings = models.Count("hedge_position__fundings"),
        hedge_position_settlements= models.Count("hedge_position__settlements"),
    ).filter(
        hedge_position_fundings=1,
        hedge_position_settlements=1,

        hedge_position__isnull=False,
        settlement__isnull=True,
    ).update(
        settlement_id=settlement_id_subquery,
    )

def set_hedge_position_offer_starting_oracle_messages():
    message_subquery = models.Subquery(
        PriceOracleMessage.objects.filter(
            # nested subquery since "hedge_position_offer__oracle_pubkey" wouldn't work
            pubkey=models.Subquery(
                HedgePositionOffer.objects.filter(
                    id=models.OuterRef(models.OuterRef("hedge_position_offer_id"))
                ).values("oracle_pubkey")[:1]
            ),
            message_sequence=models.OuterRef("oracle_message_sequence"),
        ).values("message")[:1]
    )

    signature_subquery = models.Subquery(
        PriceOracleMessage.objects.filter(
            pubkey=models.Subquery(
                HedgePositionOffer.objects.filter(
                    id=models.OuterRef(models.OuterRef("hedge_position_offer_id"))
                ).values("oracle_pubkey")[:1]
            ),
            message_sequence=models.OuterRef("oracle_message_sequence"),
        ).values("signature")[:1]
    )

    return HedgePositionOfferCounterParty.objects.filter(
        models.Q(starting_oracle_message="") | models.Q(starting_oracle_signature="")
    ).update(
        starting_oracle_message=message_subquery,
        starting_oracle_signature=signature_subquery,
    )
