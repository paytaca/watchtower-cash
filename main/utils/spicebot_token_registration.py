from main.models import Token, User, SlpAddress, Subscription, Subscriber, SendTo
import logging

logger = logging.getLogger(__name__)

class SpicebotTokens(object):

    def __init__(self, id=2):
        user = User.objects.get(id=id) #spicebot production use
        self.subscriber = user.subscriber
        subscription = self.subscriber.subscription.all()
        ids = subscription.filter(token__name='spice').distinct('slp__address').values_list('slp__id')
        self.slp_addresses = SlpAddress.objects.filter(id__in=ids)
        self.spicebot_target_address = id

    def register(self,  token_id, token_name):
        self.token , created = Token.objects.get_or_create(
            name=token_name,
            tokenid=token_id
        )


    def subscribe_to_address(self, user_id, token_address, destination_address, tokenid, tokenname):
        response = {'success': False}
        if user_id and token_address and destination_address and tokenname:
            subscriber_qs = Subscriber.objects.filter(user_id=user_id)
            if subscriber_qs.exists():
                subscriber = subscriber_qs.first()
                sendto_obj = SendTo.objects.get(address=destination_address)
                token_obj =  Token.objects.get(tokenid=tokenid)
                address_obj = SlpAddress.objects.get(address=token_address)
                subscription_obj, created= Subscription.objects.get_or_create(slp=address_obj, token=token_obj)
                
                # subscription_obj.token = token_obj
                # subscription_obj.save()
                subscription_obj.address.add(sendto_obj)
                subscriber.subscription.add(subscription_obj)
                response['success'] = True
        return response

    def subscribe(self):
        total = self.slp_addresses.count()
        counter = 1
        for slp in self.slp_addresses:
            print(f'subscribing {counter} out of {total} | {slp}')
            response = self.subscribe_to_address(
                self.subscriber.id,
                slp.address,
                'https://spicebot.scibizinformatics.com/watchtower/',
                self.token.tokenid,
                self.token.name
            )
            if response['success']:
                counter += 1 
            