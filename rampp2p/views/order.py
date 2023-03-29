from rest_framework.views import APIView

# OrderListView
class OrderListView(APIView):
  """
  List Order instances
  """

# OrderStatusListView
class OrderStatusListView(APIView):
  """
  List an order's status history
  """

# OrderDetailView
class OrderDetailView(APIView):
  """
  Retrieve and create an Order instance.
  """

# OrderStatusDetailView
class OrderStatusDetailView(APIView):
  """
  Retrieve an order status instance
  """