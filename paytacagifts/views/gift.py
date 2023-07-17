from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.response import Response

from paytacagifts.serializers import (ListGiftsResponseSerializer, CreateGiftPayloadSerializer, ClaimGiftPayloadSerializer,
                                    ClaimGiftResponseSerializer,RecoverGiftResponseSerializer, RecoverGiftPayloadSerializer,
                                    CreateGiftResponseSerializer)
from paytacagifts.models import Gift, Wallet, Campaign, Claim

from drf_yasg import openapi
from drf_yasg.utils import swagger_auto_schema
from django.db.models import Sum
from datetime import datetime

class GiftViewSet(viewsets.GenericViewSet):
    lookup_field = "wallet_hash"

    @action(detail=True, methods=['get'])
    @swagger_auto_schema(
        operation_description="Fetches a list of Gifts filtered by wallet hash with pagination.",
        responses={
            status.HTTP_200_OK: ListGiftsResponseSerializer
        },
        manual_parameters=[
            openapi.Parameter('offset', openapi.IN_QUERY, description="Offset for pagination.", type=openapi.TYPE_INTEGER),
            openapi.Parameter('limit', openapi.IN_QUERY, description="Limit for pagination.", type=openapi.TYPE_INTEGER),
            openapi.Parameter('claimed', openapi.IN_QUERY, description="Limit for pagination.", type=openapi.TYPE_BOOLEAN, default=None),
            openapi.Parameter('campaign', openapi.IN_QUERY, description="Limit for pagination.", type=openapi.TYPE_INTEGER),
        ]
    )
    def list_gifts(self, request, wallet_hash=None):
        count = None
        claimed = None
        campaign_filter = None
        offset = 0
        limit = 0
        query_args = request.query_params
        wallet_hash = self.kwargs[self.lookup_field]
        
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
        queryset = queryset.order_by('-date_created')
        if offset:
            queryset = queryset[offset:]
        if limit:
            queryset = queryset[:limit]

        gifts = []
        for gift in queryset:
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
        
    @swagger_auto_schema(
        request_body=CreateGiftPayloadSerializer,
        responses={status.HTTP_200_OK: CreateGiftResponseSerializer},
        manual_parameters=[
            openapi.Parameter('wallet_hash', openapi.IN_PATH, description="Wallet Hash", type=openapi.TYPE_STRING, required=True),
        ]
    )
    def create(self, request, *args, **kwargs):
        data = request.data
        wallet_hash = kwargs.get("wallet_hash", "")
        if not wallet_hash: raise Exception('Wallet Hash Required')
        wallet = Wallet.objects.get(wallet_hash=wallet_hash)
        if "campaign" in data:
            if "limit_per_wallet" in data["campaign"]:
                limit = data["campaign"]["limit_per_wallet"]
                name = data["campaign"]["name"]
                campaign = Campaign.objects.create(name=name, wallet=wallet, limit_per_wallet=limit)
            elif "id" in data["campaign"]:
                campaign = Campaign.objects.get(id=data["campaign"]["id"])
        else:
            campaign = None
        gift, created = Gift.objects.get_or_create(
            gift_code_hash=data["gift_code_hash"],
            wallet=wallet
        )
        if created:
            gift.address=data["address"]
            gift.amount=data["amount"]
            gift.share=data["share"]
            gift.campaign=campaign
            gift.save()
        return Response({"gift": str(gift)})

    @action(detail=True, methods=['post'])
    @swagger_auto_schema(
        operation_description="Claim a Gift record.",
        request_body=ClaimGiftPayloadSerializer,
        responses={
            status.HTTP_200_OK: ClaimGiftResponseSerializer
        }
    )
    def claim(self, request, gift_code_hash):
        wallet_hash = request.data["wallet_hash"]
        wallet, _ = Wallet.objects.get_or_create(wallet_hash=wallet_hash)
        gift_qs = Gift.objects.filter(gift_code_hash=gift_code_hash)
        if not gift_qs.exists():
            raise Exception("Gift does not exist!")
        gift = gift_qs.first()
        claim = Claim.objects.filter(gift=gift.id, wallet=wallet).first()
        if claim:
            return Response({
                "share": gift.share,
                "claim_id": str(claim.id)
            })

        if gift.campaign:
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
    @swagger_auto_schema(
        operation_description="Recover a Gift record, which deletes this record from the database",
        request_body=RecoverGiftPayloadSerializer,
        responses={status.HTTP_200_OK: RecoverGiftResponseSerializer}
    )
    def recover(self, request, gift_code_hash):
        wallet_hash = request.data["wallet_hash"]
        wallet, _ = Wallet.objects.get_or_create(wallet_hash=wallet_hash)
        gift_qs = Gift.objects.filter(wallet=wallet, gift_code_hash=gift_code_hash, date_claimed__isnull=True)
        if not gift_qs.exists():
            raise Exception("Gift does not exist!")
        gift = gift_qs.first()
        gift_share = gift.share
        # Do not delete, just mark as claimed
        gift.date_claimed = datetime.now()
        gift.save()
        # gift_id = gift.id
        # gift.delete()
        return Response({
            "share": gift_share
        })
