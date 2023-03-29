from rest_framework.views import APIView

# PaymentTypeListView
class PaymentTypeListView(APIView):
  """
  List PaymentType instances
  """

# PaymentMethodListView
class PaymentMethodListView(APIView):
  """
  List PaymentMethod instances
  Filters by peer, ad, order
  """

# PaymentTypeDetailView
class PaymentTypeDetailView(APIView):
  """
  CRUD a PaymentType instance.
  """

# PaymentMethodDetailView
class PaymentMethodDetailView(APIView):
  """
  CRUD a PaymentMethod instance.
  """