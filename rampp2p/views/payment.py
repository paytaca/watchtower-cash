from rest_framework import generics
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticatedOrReadOnly
from rest_framework import status
from django.http import Http404
from django.contrib.auth.decorators import user_passes_test
from django.core.exceptions import ValidationError
from ..models.payment import PaymentType, PaymentMethod
from ..models.peer import Peer
from ..serializers.payment import PaymentTypeSerializer, PaymentMethodSerializer
from ..utils import verify_signature

# TODO Add permission to PaymentTypes's write endpoints

class PaymentTypeList(APIView):
  # permission_classes = [IsAuthenticatedOrReadOnly]

  def get(self, request):
    queryset = PaymentType.objects.all()
    serializer = PaymentTypeSerializer(queryset, many=True)
    return Response(serializer.data, status.HTTP_200_OK)

  def post(self, request):
    serializer = PaymentTypeSerializer(data=request.data)
    if serializer.is_valid():
      serializer.save()
      return Response(serializer.data, status=status.HTTP_200_OK)
    return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

class PaymentTypeDetail(APIView):
  # permission_classes = [IsAuthenticatedOrReadOnly]

  def get_object(self, pk):
    try:
      payment_type = PaymentType.objects.get(pk=pk)
    except PaymentType.DoesNotExist:
      raise Http404

  def get(self, request, pk):
    payment_type = self.get_object(pk)
    serializer = PaymentTypeSerializer(payment_type)
    return Response(serializer.data, status=status.HTTP_200_OK)

  def put(self, request, pk):
    payment_type = self.get_object(pk)
    serializer = PaymentTypeSerializer(payment_type, data=request.data)
    if serializer.is_valid():
      serializer.save()
      return Response(serializer.data, status=status.HTTP_200_OK)
    return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

  def delete(self, request, pk):
    payment_type = self.get_object(pk)
    payment_type.delete()
    return Response(status=status.HTTP_204_NO_CONTENT)

class PaymentMethodListCreate(APIView):
  def post(self, request):

    # TODO: verify signature
    # try:
    #   verify_signature(request)
    # except ValidationError as err:
    #   return Response(err.args[0], status=status.HTTP_403_FORBIDDEN)

    serializer = PaymentMethodSerializer(data=request.data)
    if serializer.is_valid():
      # serializer.owner = Peer.objects.get(wallet_hash=request.data['wallet_hash'])
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
  
class PaymentMethodDetail(generics.RetrieveUpdateDestroyAPIView):
  # TODO only valid users can perform this action. i.e. owner of payment method
  queryset = PaymentMethod.objects.all()
  serializer_class = PaymentMethodSerializer