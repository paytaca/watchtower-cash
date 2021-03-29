
from django.contrib.auth import get_user_model
from main.models import Subscription, SlpAddress, BchAddress, Recipient, Token
User = get_user_model()

def subscribe_to_address(user_id, token_address, destination_address, tokenid, tokenname):
    response = {'success': False}
    # if user_id and token_address and destination_address and tokenname:
    #     subscriber_qs = Subscriber.objects.filter(user_id=user_id)
    #     if subscriber_qs.exists():
    #         subscriber = subscriber_qs.first()
    #         sendto_obj, created = SendTo.objects.get_or_create(address=destination_address)
    #         if 'bitcoincash' in token_address:
    #             address_obj, created = BchAddress.objects.get_or_create(address=token_address)
    #             subscription_obj, created = Subscription.objects.get_or_create(bch=address_obj)
    #             reason = 'BCH added.'
    #         else:
    #             address_obj, created = SlpAddress.objects.get_or_create(address=token_address)
    #             subscription_obj, created = Subscription.objects.get_or_create(slp=address_obj)
    #             reason = 'SLP added.'
    #         token_obj, created =  Token.objects.get_or_create(tokenid=tokenid)
    #         token_obj.name = tokenname.lower()
    #         subscription_obj.token = token_obj
    #         subscription_obj.save()
    #         subscription_obj.address.add(sendto_obj)
    #         subscriber.subscription.add(subscription_obj)
    #         response['success'] = True
    return response