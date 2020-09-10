from main.models import Token, Subscription

def check_wallet_address_subscription(address):
    for token_obj in Token.objects.all():
        if 'bitcoincash' in address:
            subscription = Subscription.objects.filter(
                bch__address=address             
            )
        else:
            subscription = Subscription.objects.filter(
                slp__address=address, 
                token=token_obj
            )
        if subscription.exists():
            break
    return subscription