# Ideally put all files/code pulled from outside the app(anyhedge) in here
from main.utils.queries.bchd import BCHDQuery
from notifications.utils.send import send_push_notification_to_wallet_hashes, NotificationTypes
from main.models import TransactionMetaAttribute
from main.tasks import parse_tx_wallet_histories

def get_bchd_instance():
    return BCHDQuery()
