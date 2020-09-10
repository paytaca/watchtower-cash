from django.contrib.auth imoprt get_user_model
from main.models import Subscriber, Token
User = get_user_model()

def spicebot_token_subscription(token_obj):
    # check if this token is under spicebot subscription
    user = User.objects.get(username='spicebot-production')
    subscriber = Subscriber.objects.get(user=user)
    return subscriber.subscription.filter(token=token_obj).exists()
    
def check_token_subscription(transaction_token, subscribed_token_id):
    subscribed_token = Token.objects.get(id=subscribed_token_id)
    try:
        token_obj = Token.objects.get(tokenid=transaction_token)
    except ObjectDoesNotExist:
        token_obj = Token.objects.get(name=transaction_token)
    if token_obj != subscribed_token:
        valid = spicebot_token_subscription(token_obj)
    else:
        valid = True
    return valid, token_obj
