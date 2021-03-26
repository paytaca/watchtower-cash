from main.models import Token,BchAddress, Subscription, SlpAddress, Recipient
from django.conf import settings
from django.db import transaction as trans

def remove_subscription(token_address, token_id, subscriber_id, platform):
    token = Token.objects.get(id=token_id)
    platform = platform.lower()
    subscriber = None

    # if platform == 'telegram':
    #     subscriber = Subscriber.objects.get(telegram_user_details__id=subscriber_id)
    # elif platform == 'slack':
    #     subscriber = Subscriber.objects.get(slack_user_details__id=subscriber_id)
    
    # if token and subscriber:
    #     if token_address.startswith('bitcoincash'):
    #         address_obj = BchAddress.objects.get(address=token_address)
    #         subscription = Subscription.objects.filter(
    #             bch=address_obj,
    #             token=token
    #         )
    #     else:
    #         address_obj = SlpAddress.objects.get(address=token_address)
    #         subscription = Subscription.objects.filter(
    #             slp=address_obj,
    #             token=token
    #         ) 
        
    #     if subscription.exists():
    #         subscription.delete()
    #         return True
    
    return False

def save_subscription(token_address, token_id, subscriber_id, platform):
    # note: subscriber_id: unique identifier of telegram/slack user
    token = Token.objects.get(id=token_id)
    platform = platform.lower()
    subscriber = None

    # check telegram & slack user fields in subscriber
    if platform == 'telegram':
        subscriber = Subscriber.objects.get(telegram_user_details__id=subscriber_id)
    elif platform == 'slack':
        subscriber = Subscriber.objects.get(slack_user_details__id=subscriber_id)

    if token and subscriber:
        destination_address = None

        if token_address.startswith('bitcoincash'):
            address_obj, created = BchAddress.objects.get_or_create(address=token_address)
            subscription_obj, created = Subscription.objects.get_or_create(
                bch=address_obj,
                token=token
            )
        else:
            address_obj, created = SlpAddress.objects.get_or_create(address=token_address)
            subscription_obj, created = Subscription.objects.get_or_create(
                slp=address_obj,
                token=token
            ) 

        if platform == 'telegram':
            destination_address = settings.TELEGRAM_DESTINATION_ADDR
        elif platform == 'slack':
            destination_address = settings.SLACK_DESTINATION_ADDR

        if created:
            with trans.atomic():
                sendTo, created = SendTo.objects.get_or_create(address=destination_address)

                subscription_obj.address.add(sendTo)
                subscription_obj.token = token
                subscription_obj.save()
                
                subscriber.subscription.add(subscription_obj)
            return True

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