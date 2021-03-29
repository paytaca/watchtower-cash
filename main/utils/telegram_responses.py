MESSAGES = {}

MESSAGES['default'] = f"""Welcome to WatchTower telegram bot!

\nSubscribe now and receive notifications everytime transactions are made on any of your subscribed addresses!
\nSee /help for my list of commands.
"""

MESSAGES['help'] = """Hello! Here's a list of my commands:

\n<b>/subscribe (SLP or BCH address)</b> - to register your address and get notified.
\n<b>/unsubscribe (SLP or BCH address)</b> - to unregister your address.
"""


def get_message(key):
	return MESSAGES[key]