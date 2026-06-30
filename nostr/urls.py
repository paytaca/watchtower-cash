from django.urls import path
from rest_framework import routers
from .views import (
    PubkeyRegisterView,
    PubkeyUnregisterView,
    PubkeyCheckView,
    PubkeyLastOnlineView,
    PubkeyTouchView,
    ShowActiveStatusView,
    NostrRoomListView,
    NostrRoomDetailView,
    NostrRoomBatchSyncView,
    NostrBlockListView,
    NostrBlockContactView,
    NostrBlockGroupView,
)

router = routers.DefaultRouter()

urlpatterns = router.urls + [
    path("register/", PubkeyRegisterView.as_view(), name='nostr-register'),
    path("unregister/", PubkeyUnregisterView.as_view(), name='nostr-unregister'),
    path("check/<str:pubkey_hex>/", PubkeyCheckView.as_view(), name='nostr-check'),
    path("last-active/", PubkeyLastOnlineView.as_view(), name='nostr-last-active'),
    path("touch/", PubkeyTouchView.as_view(), name='nostr-touch'),
    path("active-status/", ShowActiveStatusView.as_view(), name='nostr-active-status'),
    path("rooms/batch-sync/", NostrRoomBatchSyncView.as_view(), name='nostr-rooms-batch-sync'),
    path("rooms/<str:room_id>/", NostrRoomDetailView.as_view(), name='nostr-room-detail'),
    path("rooms/", NostrRoomListView.as_view(), name='nostr-rooms'),
    path("blocks/contacts/<str:pub_key_hex>/", NostrBlockContactView.as_view(), name='nostr-unblock-contact'),
    path("blocks/contacts/", NostrBlockContactView.as_view(), name='nostr-block-contact'),
    path("blocks/groups/<str:room_id>/", NostrBlockGroupView.as_view(), name='nostr-unblock-group'),
    path("blocks/groups/", NostrBlockGroupView.as_view(), name='nostr-block-group'),
    path("blocks/", NostrBlockListView.as_view(), name='nostr-blocks'),
]
