from rest_framework import generics
from ..models.status import Status
from ..serializers.status import StatusSerializer

class StatusList(generics.ListAPIView):
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
