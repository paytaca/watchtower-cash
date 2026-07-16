import threading
from contextlib import contextmanager

_suppression = threading.local()

@contextmanager
def suppress_transaction_post_save_delay():
    old = getattr(_suppression, 'skip_delay', False)
    _suppression.skip_delay = True
    try:
        yield
    finally:
        _suppression.skip_delay = old

def is_transaction_post_save_delay_suppressed():
    return getattr(_suppression, 'skip_delay', False)
