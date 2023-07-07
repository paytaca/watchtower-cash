from rest_framework import viewsets
from rest_framework.decorators import action
from rest_framework.response import Response

from paytacagifts.models import Gift, Wallet, Campaign, Claim


class GiftViewSet(viewsets.ViewSet):
    lookup_field = "gift_code_hash"

    def list(self, request, wallet_hash=None):
        count = None
        claimed = None
        campaign_filter = None
        offset = 0
        limit = 0
        query_args = request.query_params

        if query_args.get("offset"):
            offset = int(query_args.get("offset"))

        if query_args.get("limit"):
            limit = int(query_args.get("limit"))

        if query_args.get("claimed"):
            claimed = query_args.get("claimed", None)
            if claimed is not None:
                claimed = str(claimed).lower().strip() == "true"

        if query_args.get("campaign"):
            campaign_filter = query_args.get("campaign", None)

        queryset = Gift.objects.filter(wallet__wallet_hash=wallet_hash)
        if isinstance(claimed, bool):
            queryset = queryset.filter(date_claimed__isnull=not claimed)

        if isinstance(campaign_filter, str):
            queryset = queryset.filter(campaign__id=campaign_filter)

        count = queryset.count()
        if offset:
            queryset = queryset[offset:]
        if limit:
            queryset = queryset[:limit]

        gifts = []
        for gift in queryset.order_by('-date_created'):
            gift.fetch_related("campaign")
            campaign = gift.campaign
            campaign_id = None
            campaign_name = None
            if campaign:
                campaign_id = str(campaign.id)
                campaign_name = str(campaign.name)
            gifts.append({
                "gift_code_hash": str(gift.gift_code_hash),
                "date_created": str(gift.date_created),
                "amount": gift.amount,
                "campaign_id": campaign_id,
                "campaign_name": campaign_name,
                "date_claimed": str(gift.date_claimed)
            })

        data = {
            "gifts": gifts,
            "pagination": {
                "count": count,
                "offset": offset,
                "limit": limit,
            }
        }
        return Response(data)

    def create(self, request, wallet_hash=None):
        data = request.data
        wallet, _ = Wallet.objects.get_or_create(wallet_hash=wallet_hash)
        if "campaign" in data:
            if "limit_per_wallet" in data["campaign"]:
                limit = data["campaign"]["limit_per_wallet"]
                name = data["campaign"]["name"]
                campaign = Campaign.objects.create(name=name, wallet=wallet, limit_per_wallet=limit)
            elif "id" in data["campaign"]:
                campaign = Campaign.objects.get(id=data["campaign"]["id"])
        else:
            campaign = None

        gift = Gift.objects.create(
            gift_code_hash=data["gift_code_hash"],
            address=data["address"],
            wallet=wallet,
            amount=data["amount"],
            share=data["share"],
            campaign=campaign
        )
        return Response({"gift": str(gift)})

    @action(detail=True, methods=['post'])
    def claim(request, gift_code_hash):
        wallet_hash = request.data["wallet_hash"]
        wallet, _ = Wallet.objects.get_or_create(wallet_hash=wallet_hash)
        gift = Gift.objects.filter(gift_code_hash=gift_code_hash).first()
        if gift is None:
            raise Exception("Gift does not exist!")

        claim = Claim.objects.filter(gift=gift.id, wallet=wallet).first()
        if claim:
            return Response({
                "share": gift.share,
                "claim_id": str(claim.id)
            })

        gift.fetch_related('campaign')
        if gift.campaign:
            gift.campaign.fetch_related('claims')
            claims = gift.campaign.claims.all()
            claims_sum = claims.aggregate(Sum('amount'))['amount__sum'] or 0
            if claims_sum < gift.campaign.limit_per_wallet:
                claim = Claim.objects.create(
                    wallet=wallet,
                    amount=gift.amount,
                    gift=gift,
                    campaign=gift.campaign
                )
            else:
                raise Exception("You have exceeded the limit of gifts to claim for this campaign")
        else:
            claim = Claim.objects.create(
                wallet=wallet,
                amount=gift.amount,
                gift=gift
            )

        if claim:
            gift.date_claimed = datetime.now()
            gift.save()
            return Response({
                "share": gift.share,
                "claim_id": str(claim.id)
            })
        else:
            raise Exception("This gift has been claimed")

    @action(detail=True, methods=['post'])
    def recover(request, gift_code_hash):
        wallet_hash = request.data["wallet_hash"]
        wallet, _ = Wallet.objects.get_or_create(wallet_hash=wallet_hash)
        gift = Gift.objects.filter(wallet=wallet, gift_code_hash=gift_code_hash, date_claimed__isnull=True).first()
        if gift is None:
            raise Exception("Gift does not exist!")

        gift_share = gift.share
        gift_id = gift.id
        gift.delete()
        return Response({
            "share": gift_share
        })
