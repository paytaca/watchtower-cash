from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from main.utils.recipient import Recipient as RecipientScript
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
        telegram_id = request.data.get('telegram_id', None)
        response = {'success': False}
        response_status = status.HTTP_409_CONFLICT
        if address is not None:
            address = address.lower()
            if address.startswith('bitcoincash:') or address.startswith('simpleledger:'):
                obj_recipient = RecipientScript(
                    web_url=web_url,
                    telegram_id=telegram_id
                )
                recipient, created = obj_recipient.get_or_create()
                                
                if recipient and not created:
                    # Renew validity.
                    recipient.valid = True
                    recipient.save()     
                    
                bch = None
                slp = None

                if address.startswith('simpleledger'):
                    slp, _ = SlpAddress.objects.get_or_create(address=address)
                    
                elif address.startswith('bitcoincash'):
                    bch, _ = BchAddress.objects.get_or_create(address=address)
                
                _, created = Subscription.objects.get_or_create(
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
