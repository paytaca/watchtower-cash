from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from main.models import (
    Subscription,
    Recipient,
    SlpAddress,
    BchAddress
)


class SubscribeViewSet(APIView):
    
    def post(self, request, format=None):
        address = request.data.get('address', None)
        web_url = request.data.get('web_url', None)
        response = {'success': False}
        response_status = status.HTTP_409_CONFLICT
        if address and web_url:
            if web_url.lower().startswith('http'):
                address = address.lower()
                if address.startswith('bitcoincash:') or address.startswith('simpleledger:'):
                    
                    recipient, created = Recipient.objects.get_or_create(web_url=web_url)
                    if not created:
                        # Renewed web_url validity.
                        recipient.valid = True
                        recipient.save()
                    bch = None
                    slp = None

                    if address.startswith('simpleledger'):
                        slp, _ = SlpAddress.objects.get_or_create(address=address)
                    elif address.startswith('bitcoincash'):
                        bch, _ = BchAddress.objects.get_or_create(address=address)
                    
                    subscription, created = Subscription.objects.get_or_create(
                        recipient=recipient,
                        slp=slp,
                        bch=bch
                    )
                    if created:
                        response['success'] = True
                        response_status = status.HTTP_200_OK
                    else:
                        response['error'] = 'subscription_already_exists'
        return Response(response, status=response_status)
