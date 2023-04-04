from rest_framework import generics, status
from rest_framework.views import APIView
from rest_framework.response import Response
from ..serializers.order import OrderSerializer
from ..serializers.status import StatusSerializer
from ..models.order import Order
from ..models.status import Status

class OrderListCreate(APIView):
  def post(self, request):
    serializer = OrderSerializer(data=request.data)
    if serializer.is_valid():
      serializer.save()
      return Response(serializer.data, status=status.HTTP_201_CREATED)
    return Response(serializer.data, status=status.HTTP_400_BAD_REQUEST)

  def get(self, request):
    queryset = Order.objects.all()
    creator = request.query_params.get("creator", None)
    if creator is not None:
      queryset = queryset.filter(creator=creator)
    serializer = OrderSerializer(queryset, many=True)
    return Response(serializer.data, status.HTTP_200_OK)

  # TODO override .create method to create a Status=SUBMITTED status

class OrderDetail(generics.RetrieveAPIView):
  queryset = Order.objects.all();
  serializer_class = OrderSerializer

# TODO require Ad owner authentication
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
class OrderStatusList(generics.ListAPIView):
  """
  List order's statuses
  """

  serializer_class = StatusSerializer
  
  # returns filtered data by order_id 
  # if query_param 'order_id' exists
  def get_queryset(self):
    queryset = Status.objects.all()
    order = self.request.query_params.get('order_id', None)
    if order is not None:
      queryset = queryset.filter(order=order)
    return queryset
