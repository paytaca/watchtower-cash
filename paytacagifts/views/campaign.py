from rest_framework import viewsets
from rest_framework.response import Response
from django.db.models import Count
from paytacagifts import models, serializers
from rest_framework.decorators import action


class CampaignViewSet(viewsets.ViewSet):
    lookup_field = "wallet_hash"

    @action(detail=True, methods=['post'])
    def get_campaigns(request, wallet_hash):
        offset = int(request.query_params.get("offset", 0))
        limit = int(request.query_params.get("limit", 0))

        queryset = models.Campaign.objects.filter(wallet__wallet_hash=wallet_hash)
        count = queryset.aggregate(count=Count('id'))['count']

        if offset:
            queryset = queryset[offset:]
        if limit:
            queryset = queryset[:limit]

        campaigns = []
        for campaign in queryset.order_by('-date_created'):
            campaign.gifts = campaign.gifts.count()
            campaign.claims = campaign.claims.count()
            campaigns.append(serializers.CampaignSerializer(campaign).data)

        data = {
            'campaigns': campaigns,
            'pagination': {
                'count': count,
                'offset': offset,
                'limit': limit,
            }
        }
        return Response(data)
