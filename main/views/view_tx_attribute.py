from rest_framework import generics
from rest_framework.response import Response

from main.serializers import TransactionMetaAttributeSerializer

class TransactionMetaAttributeView(generics.GenericAPIView):
    serializer_class = TransactionMetaAttributeSerializer

    def post(self, request, *args, **kwargs):
        serializer = self.serializer_class(data=request.data)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        if not serializer.instance:
            return Response()

        return Response(serializer.data)
