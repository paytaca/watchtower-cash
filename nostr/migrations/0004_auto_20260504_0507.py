# No-op: the index this migration removed (nostr_nostr_pubkey__6590fe_idx)
# only ever existed on the deleted NostrPubkeyDevice model, and the index it
# added (nostr_nostr_pubkey__046ea9_idx) was already created by 0003.
# Kept as an empty migration because 0005 depends on it.

from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('nostr', '0003_refactor_nostr_pubkey'),
    ]

    operations = []
