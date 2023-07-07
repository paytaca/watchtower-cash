from rest_framework import viewsets, status
from rest_framework.response import Response
from rest_framework.decorators import action

from drf_yasg.utils import swagger_auto_schema
from drf_yasg import openapi

from django.db.models import Count
from paytacagifts import models, serializers
from paytacapos.pagination import CustomLimitOffsetPagination


class CampaignViewSet(viewsets.GenericViewSet):
    lookup_field = "wallet_hash"
    pagination_class = CustomLimitOffsetPagination

    @action(detail=True, methods=['get'])
    @swagger_auto_schema(
        operation_description="Fetches a list of Campaigns filtered by wallet hash with pagination.",
        responses={status.HTTP_200_OK: serializers.ListCampaignsResponseSerializer},
        manual_parameters=[
            openapi.Parameter('offset', openapi.IN_QUERY, description="Offset for pagination.", type=openapi.TYPE_INTEGER),
            openapi.Parameter('limit', openapi.IN_QUERY, description="Limit for pagination.", type=openapi.TYPE_INTEGER)
        ]
    )
    def list_campaigns(request, wallet_hash):
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
