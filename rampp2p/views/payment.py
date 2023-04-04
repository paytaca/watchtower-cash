from rest_framework import generics
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from ..models.payment import PaymentType, PaymentMethod
from ..serializers.payment import PaymentTypeSerializer, PaymentMethodSerializer
import logging
LOGGER = logging.getLogger(__name__)

class PaymentTypeListCreate(generics.ListCreateAPIView):
  """
  List/Create a PaymentType instance
  """

  queryset = PaymentType.objects.all()
  serializer_class = PaymentTypeSerializer
  # TODO: must require admin access

class PaymentTypeDetail(generics.RetrieveUpdateDestroyAPIView):
  """
  Retrieve/Update/Delete a PaymentType instance.
  """

  queryset = PaymentType.objects.all()
  serializer_class = PaymentTypeSerializer
  
class PaymentMethodDetail(generics.RetrieveUpdateDestroyAPIView):
  """
  Retrieve/Update/Destroy a PaymentMethod instance.
  """

  queryset = PaymentMethod.objects.all()
  serializer_class = PaymentMethodSerializer

class PaymentMethodListCreate(APIView):
  def post(self, request):
    serializer = PaymentMethodSerializer(data=request.data)
    if serializer.is_valid():
      serializer.save()
      return Response(serializer.data, status=status.HTTP_201_CREATED)
    return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
  
  def get(self, request):
    
    queryset = PaymentMethod.objects.all()
    owner = request.query_params.get("owner", None)
    if owner is not None:
      queryset = queryset.filter(owner=owner)
    serializer = PaymentMethodSerializer(queryset, many=True)
    return Response(serializer.data, status.HTTP_200_OK)