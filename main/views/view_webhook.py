from rest_framework import viewsets, status
from rest_framework.response import Response
from rest_framework.decorators import action

from main.serializers import BcmrWebhookSerializer
from main.models import CashFungibleToken, CashTokenInfo


class BcmrWebhookViewSet(viewsets.GenericViewSet):
    serializer_class = BcmrWebhookSerializer

    @action(methods=['POST'], detail=False)
    def webhook(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        info_dict = {
            'name': serializer.validated_data['name'],
            'description': serializer.validated_data['description'],
            'symbol': serializer.validated_data['symbol'],
            'decimals': serializer.validated_data['decimals'],
            'image_url': serializer.validated_data['image_url']
        }

        info = CashTokenInfo.objects.filter(**info_dict)
        cashtoken, _ = CashFungibleToken.objects.get_or_create(
            category=serializer.validated_data['category']
        )

        if info.exists():
            cashtoken.info = info.first()
        else:
            info = CashTokenInfo(**info_dict)
            info.save()
            cashtoken.info = info
            
        cashtoken.save()

        return Response(serializer.data, status=status.HTTP_200_OK)
