# Generated manually

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('nostr', '0002_auto_20260503_0928'),
    ]

    operations = [
        migrations.DeleteModel(
            name='NostrPubkeyDevice',
        ),
        migrations.CreateModel(
            name='NostrPubkey',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('pubkey_hex', models.CharField(db_index=True, max_length=64)),
                ('wallet_hash', models.CharField(db_index=True, max_length=70, unique=True)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('last_active', models.DateTimeField(auto_now=True)),
            ],
        ),
        migrations.AddIndex(
            model_name='nostrpubkey',
            index=models.Index(fields=['pubkey_hex', 'wallet_hash'], name='nostr_nostr_pubkey__046ea9_idx'),
        ),
    ]
