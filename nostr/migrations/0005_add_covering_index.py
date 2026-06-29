from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('nostr', '0004_auto_20260504_0507'),
    ]

    operations = [
        migrations.RemoveIndex(
            model_name='nostrpubkey',
            name='nostr_nostr_pubkey__046ea9_idx',
        ),
        migrations.AddIndex(
            model_name='nostrpubkey',
            index=models.Index(
                fields=['pubkey_hex', 'wallet_hash', 'last_active'],
                name='nostr_nostr_pubkey__046ea9_idx',
            ),
        ),
    ]
