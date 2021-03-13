from django.contrib.auth import get_user_model
from main.models import Subscriber, Token, Subscription
User = get_user_model()
from django.core.exceptions import ObjectDoesNotExist

def spicebot_token_subscription(token_obj):
    # check if this token is under spicebot subscription
    user = User.objects.get(username='spicebot-production')
    subscriber = Subscriber.objects.get(user=user)
    return subscriber.subscription.filter(token=token_obj).exists()
    
def check_token_subscription(token_id, subscription_id):
    subscription = Subscription.objects.get(id=subscription_id)
    if subscription.token:
        if subscription.token.tokenid != token_id:
            return False
    return True