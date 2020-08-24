from rest_framework.viewsets import ViewSet
from drf_yasg.utils import swagger_auto_schema

class Account(ViewSet):
    
    @swagger_auto_schema(method="post", request_body=DeliverRatesRequestSerializer, responses={200: DeliveryRateSerializer(many=True)})
    @action(detail=False, url_path="create", methods=["post"])
    def create_account(self, request), *args, **kwargs):

        rates = get_delivery_rates(
            distance=request_serializer.get_distance(),
            shop=getattr(request, "shop", None),
            as_json=False,
        )

        response_serializer = DeliveryRateSerializer(rates, many=True)
        # this is just temporary
        data = {
            "rates": response_serializer.data
        }
        return Response(data=data, status=200)


        action = request.POST['action']
        status = 'failed'
        if action == 'register':
            firstname = request.POST['firstname']
            lastname = request.POST['lastname']
            email = request.POST['email']
            password = request.POST['password']
            username = request.POST['username']
            # Create User
            user = User()
            user.username = username
            user.first_name = firstname
            user.last_name = lastname
            user.email = email
            user.save()
            user.set_password(password)
            user.save()
            # Create Subscriber
            subscriber = Subscriber()
            subscriber.user = user
            subscriber.save()
            status = 'success'
            return redirect('home')
        if action == 'update':
            return redirect('account')