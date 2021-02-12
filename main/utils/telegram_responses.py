MESSAGES = {}

MESSAGES['default'] = f"""Welcome to SLP Notify telegram bot!

\nSubscribe now and receive notifications everytime transactions are made on any of your subscribed addresses!
\nSee /help for my list of commands.
"""

MESSAGES['help'] = """Hello! Here's a list of my commands:

\n<b>/subscribe (SLP or BCH address) (token)</b> - to register your address and get notified.
\n<b>/unsubscribe (SLP or BCH address) (token)</b> - to unregister your address.
"""

MESSAGES['not_connected'] = """<b>Account not yet connected</b>

\nConnect your SLP Notify account to telegram first
\nIf you haven't registered yet, go to: https://www.watchtower.com/signup"""

def get_message(key):
	return MESSAGES[key]