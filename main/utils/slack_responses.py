from django.conf import settings
from main.models import SLPToken

################## MESSAGES ##################

MESSAGES = {}

MESSAGES['default'] = '*Welcome to SLP Notify!*  :grinning:\nSubscribe now and receive notifications everytime transactions are made on any of your subscribed addresses!'
MESSAGES['subscribe'] = '*Subscribing to SLP Notify  :bell:*\nRegister your address and get notified in an instant!'
MESSAGES['unsubscribe'] = '*Removing an Address from Subscription  :no_entry:*\nStop receiving notifications for an address with a specified token'
MESSAGES['tokens'] = '*SLP Tokens Supported:  :dollar:*\nTokens supported when you subscribe using an SLP address'
MESSAGES['notification'] = f'A transaction has been made on one of your subscribed addresses'
# MESSAGES['not-connected'] = "*Slack Account Not Yet Connected*\nConnect your SLP Notify account to Slack first\n_Not yet registered to SLP Notify? Register now at https://www.facebook.com  :pencil2:_"

################## ATTACHMENTS ##################

COMMAND_TITLE = 'Command  :pencil2:'
EXAMPLES_TITLE = 'Examples  :bulb:'
DEFAULT_ATTACHMENT_TEXT = '''
_Here are help commands you can use to get to know more about SLP Notify:_
• `subscribe` = for more info on how to subscribe
• `unsubscribe` = for more info on how to unsubscribe an address
• `tokens` = see the list of tokens currently supported
'''

ATTACHMENTS = {}

ATTACHMENTS['default'] = [
    {
        "title": "Info Commands  :pencil:",
        "text": DEFAULT_ATTACHMENT_TEXT,
        "color": settings.SLACK_THEME_COLOR
    }
]

ATTACHMENTS['subscribe'] = [
    {
        "title": COMMAND_TITLE,
        "text": (
            '_To subscribe simply send me the following command:_\n'
            + '`subscribe [BCH/SLP address] [token (for SLP addresses only)]`'
        ),
        "color": settings.SLACK_THEME_COLOR
    },
    {
        "title": EXAMPLES_TITLE,
        "text": (
            '\n_SLP Address:_\n'
            + '• subscribe simpleledger:qrza35e26nnvk087qz5zv5t2skealy2v4ch7pz7vmq spice\n'
            + '• subscribe simpleledger:qrza35e26nnvk087qz5zv5t2skealy2v4ch7pz7vmq drop\n'
            + '\n_BCH Address:_\n'
            + '• subscribe bitcoincash:qzpeeu7xzrqal3pfyjalv0uufl37cp2tpu12prztjs'
         ),
        "color": settings.SLACK_THEME_COLOR
    }
]

ATTACHMENTS['unsubscribe'] = [
    {
        "title": COMMAND_TITLE,
        "text": (
            '_To unsubscribe simply send me the following command:_\n'
            + '`unsubscribe [BCH/SLP address] [token (for SLP addresses only)]`'
        ),
        "color": settings.SLACK_THEME_COLOR
    },
    {
        "title": EXAMPLES_TITLE,
        "text": (
            '\n_SLP Address:_\n'
            + '• unsubscribe simpleledger:qrza35e26nnvk087qz5zv5t2skealy2v4ch7pz7vmq spice\n'
            + '• unsubscribe simpleledger:qrza35e26nnvk087qz5zv5t2skealy2v4ch7pz7vmq drop\n'
            + '\n_BCH Address:_\n'
            + '• unsubscribe bitcoincash:qzpeeu7xzrqal3pfyjalv0uufl37cp2tpu12prztjs'
         ),
        "color": settings.SLACK_THEME_COLOR
    }
]


def get_tokens_list():
    tokens = SLPToken.objects.exclude(name__iexact='bch').order_by('name')
    text = ''
    count = 1

    for token in tokens:
        text += f'{count}. _{token.name.upper()}_\n'
        count += 1

    return text

def get_message(key):
    return MESSAGES[key]

def get_attachment(key):
    if key == 'tokens':
        return [
            {
                "text": get_tokens_list(),
                "color": settings.SLACK_THEME_COLOR
            }
        ]

    return ATTACHMENTS[key] or None


