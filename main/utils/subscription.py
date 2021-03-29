from main.models import Token,BchAddress, Subscription, SlpAddress, Recipient
from django.conf import settings
from django.db import transaction as trans

def remove_subscription(address, subscriber_id,):
    Subscription.objects.filter(
        slp=address
    ).filter(
        bch=address
    ).filter(
        telegram_id = subscriber_id
    ).delete()

    return False

def save_subscription(address, subscriber_id):
    
    subscriber = None

    destination_address = None

    if token_address.startswith('bitcoincash'):
        bch, created = BchAddress.objects.get_or_create(address=token_address)
        
    
    if token_address.startswith('simpleledger'):
        slp, created = SlpAddress.objects.get_or_create(address=token_address)

    recipient = Recipient()
    recipient.telegram = subscriber_id
    recipient.save()
        


    subscription = Subscription()
    subscription.recipient = recipient
    subscription.slp = slp
    subscription.bch = bch
    subscription.save()


    return False

def register_user(user_details, platform):
    with trans.atomic():
        platform = platform.lower()
        user_id = user_details['id']

        uname_pass = f"{platform}-{user_id}"

        new_user, created = User.objects.get_or_create(
            username=uname_pass,
            password=uname_pass
        )

        new_subscriber = Subscriber()
        new_subscriber.user = new_user
        new_subscriber.confirmed = True

        if platform == 'telegram':
            new_subscriber.telegram_user_details = user_details
        elif platform == 'slack':
            new_subscriber.slack_user_details = user_details
            
        new_subscriber.save()