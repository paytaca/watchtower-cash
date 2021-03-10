from main.models import Token, Subscription

def check_wallet_address_subscription(address):
    if 'bitcoincash' in address:
        subscription = Subscription.objects.filter(
            bch__address=address             
        )
    else:
        subscription = Subscription.objects.filter(
            slp__address=address, 
            token=token_obj
        )
    return subscription