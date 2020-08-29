from main.models import Subscription
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response
from main.serializers import SubscriptionSerializer

class SubscriptionViewSet(viewsets.ModelViewSet):
    """
    A viewset that provides the standard actions
    """
    queryset = Subscription.objects.all()
    serializer_class = SubscriptionSerializer
    http_method_names = ['get', 'post', 'head']
    
    def create(self, request):
        subscription = self.get_object()
        # serializer = PasswordSerializer(data=request.data)
        # if serializer.is_valid():
        #     user.set_password(serializer.data['password'])
        #     user.save()
        #     return Response({'status': 'password set'})
        # else:
        return Response(serializer.errors,
                        status=status.HTTP_400_BAD_REQUEST)