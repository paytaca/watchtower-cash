MESSAGES = {}

MESSAGES['telegram_default'] = f"""Welcome to SLP Notify telegram bot!
\nIf you haven't registered yet, go to:
\nhttps://slpnotify.com/signup

\nIf you're already signed up, you'll be recieving notifications from the SLP and BCH addressess you've added. See /help for list of commands.
"""

MESSAGES['telegram_help'] = """Hello! Here's a list of my commands

\n<b>/subscribe (SLP or BCH address) (token)</b> - to register your address and get notified.
<b>/tokens</b> - list of of all supported tokens.
"""

def get_message(key):
	return MESSAGES[key]