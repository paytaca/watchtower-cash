from main.models import Subscription

def check_wallet_address_subscription(address):
    if 'bitcoincash' in address:
        subscription = Subscription.objects.filter(
            bch__address=address             
        )
    else:
        subscription = Subscription.objects.filter(
            slp__address=address
        )
    return subscription
