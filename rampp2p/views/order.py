from rest_framework import generics, status
from rest_framework.views import APIView
from rest_framework.response import Response
from django.http import Http404
from ..serializers.order import OrderSerializer
from ..serializers.status import StatusSerializer
from ..models.order import Order
from ..models.status import Status, StatusType
from ..models.payment import PaymentMethod
from ..models.ad import Ad

class OrderList(APIView):

  def get(self, request):
    queryset = Order.objects.all()
    creator = request.query_params.get("creator", None)
    if creator is not None:
      queryset = queryset.filter(creator=creator)
    serializer = OrderSerializer(queryset, many=True)
    return Response(serializer.data, status.HTTP_200_OK)

  def post(self, request):
    serializer = OrderSerializer(data=request.data)
    if serializer.is_valid():
      ad = Ad.objects.get(pk=request.data.get('ad'))
      serializer.validated_data['ad'] = ad
      serializer.validated_data['crypto_currency'] = ad.crypto_currency
      serializer.validated_data['fiat_currency'] = ad.fiat_currency
      serializer.save()

      Status.objects.create(
        status=StatusType.SUBMITTED,
        order=Order.objects.get(pk=serializer.data['id'])
      )
      
      return Response(serializer.data, status=status.HTTP_201_CREATED)
    return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

class OrderStatusList(APIView):
  def get(self, request, order_id):
    queryset = Status.objects.filter(order=order_id)
    serializer = StatusSerializer(queryset, many=True)
    return Response(serializer.data, status=status.HTTP_200_OK)

class OrderDetail(APIView):
  def get_object(self, pk):
    try:
      return Order.objects.get(pk=pk)
    except Order.DoesNotExist:
      raise Http404

  def get(self, request, pk):
    order = self.get_object(pk)
    serializer = OrderSerializer(order)
    return Response(serializer.data, status=status.HTTP_200_OK)

  def put(self, request, pk):

    # TODO: verify the signature
    # try:
    #   verify_signature(request)
    # except ValidationError as err:
    #   return Response({'error': err.args[0]}, status=status.HTTP_403_FORBIDDEN)

    order = self.get_object(pk)
    serializer = OrderSerializer(order, data=request.data)
    if serializer.is_valid():
      serializer.save()
      return Response(serializer.data, status=status.HTTP_200_OK)
    return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

class ConfimOrder(APIView):

  def post(self, request):
    # TODO self.escrow_funds(data=data)
    # TODO update Order status to Status=CONFIRMED
    pass
  
  def escrow_funds(self, data):
    pass

'''
  SUBMITTED = at Order creation
  CONFIRMED = when crypto is escrowed
  PAID      = on "confirm payment"
  APPEALED  = on "appeal"
  RELEASED  = on arbiter "release"
  REFUNDED  = on arbiter "refunded"
  CANCELED  = on "cancel order" before status=CONFIRMED || on arbiter "mark canceled, refund"
'''
