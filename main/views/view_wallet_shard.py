from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework import (
    viewsets,
    mixins,
    status
)

from main.serializers import WalletShardSerializer

from drf_yasg.utils import swagger_auto_schema
from drf_yasg import openapi


class WalletShardViewSet(
    viewsets.GenericViewSet,
    mixins.CreateModelMixin
):
    serializer_class = WalletShardSerializer
    lookup_field = 'shard'

    def get_model(self):
        return self.serializer_class.Meta.model
    
    def get_object(self):
        shard = self.kwargs.get('shard', '')
        return self.get_model().objects.filter(shard=shard)

    def create(self, request, *args, **kwargs):
        shard_check = self.get_object()

        if not shard_check.exists():
            return super().create(request, *args, **kwargs)

    @action(detail=True, methods=['get'])
    @swagger_auto_schema(
        operation_description="Get the first shard of a wallet using the hash of the second and third shards.",
        responses={status.HTTP_200_OK: WalletShardSerializer},
        manual_parameters=[
            openapi.Parameter(
                'first_identifier',
                openapi.IN_QUERY,
                description='The hash of the second shard',
                type=openapi.TYPE_STRING
            ),
            openapi.Parameter(
                'second_identifier',
                openapi.IN_QUERY,
                description='The hash of the third shard',
                type=openapi.TYPE_STRING
            )
        ]
    )
    def get_first_shard(self, request):
        first_identifier = request.query_params.get('first_identifier', None)
        second_identifier = request.query_params.get('second_identifier', None)
        
        shard_check = self.get_model().objects.filter(
            first_identifier=first_identifier,
            second_identifier=second_identifier
        )

        data = None
        if shard_check.exists():
            data = shard_check.first()
        else:
            return Response(status=status.HTTP_404_NOT_FOUND, data={'message': 'No data found' })

        serializer = self.serializer_class(data)
        return Response(data=serializer.data)