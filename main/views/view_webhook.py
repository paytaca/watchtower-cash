from rest_framework import viewsets, status
from rest_framework.response import Response
from rest_framework.decorators import action

from main.serializers import BcmrWebhookSerializer
from main.tasks import get_cashtoken_meta_data


class BcmrWebhookViewSet(viewsets.GenericViewSet):
    serializer_class = BcmrWebhookSerializer

    @action(methods=['POST'], detail=False)
    def webhook(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        get_cashtoken_meta_data(
            data['category'],
            txid=data['txid'],
            index=data['index'],
            is_nft=data['is_nft'],
            commitment=data['commitment'],
            capability=data['capability'],
            from_bcmr_webhook=True
        )

        return Response(serializer.data, status=status.HTTP_200_OK)
