from enum import Enum

class ViewCode(Enum):
    ARBITER_CREATE = 'ARBITER_CREATE'
    ARBITER_CONFIG = 'ARBITER_CONFIG'
    PEER_CREATE = 'PEER_CREATE'

class WSGeneralMessageType(Enum):
    NEW_APPEAL = 'NEW_APPEAL'
    NEW_ORDER = 'NEW_ORDER'
    READ_ORDER = 'READ_ORDER'