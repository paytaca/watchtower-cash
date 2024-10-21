from rest_framework import status
from rest_framework.views import APIView
from rest_framework.response import Response


class VoucherTempView(APIView):

    def get(self, request, *args, **kwargs):
        response = { 'results': [1] }
        return Response(response, status=status.HTTP_200_OK)
