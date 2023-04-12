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
      order = Order.objects.create(
        ad = ad,
        creator = serializer.validated_data['creator'],
        fiat_amount = serializer.validated_data['fiat_amount'],
        locked_price = serializer.validated_data['locked_price'],
        crypto_currency = ad.crypto_currency,
        fiat_currency = ad.fiat_currency,
        arbiter = serializer.validated_data['arbiter']
      )
      payment_methods = PaymentMethod.objects.filter(id__in=request.data.get('payment_methods'))
      order.payment_methods.set(payment_methods)
      Status.objects.create(
        status=StatusType.SUBMITTED,
        order=order
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
