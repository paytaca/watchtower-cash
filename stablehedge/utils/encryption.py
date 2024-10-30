from django.conf import settings
from cryptography.fernet import Fernet


def encrypt_str(data:str, fernet_key:str=settings.STABLEHEDGE_FERNET_KEY):
    fernet_obj = Fernet(fernet_key)
    return fernet_obj.encrypt(data.encode()).decode()

def decrypt_str(data:str, fernet_key:str=settings.STABLEHEDGE_FERNET_KEY):
    fernet_obj = Fernet(fernet_key)
    return fernet_obj.decrypt(data.encode()).decode()
