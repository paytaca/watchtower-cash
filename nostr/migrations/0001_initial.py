from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        ('push_notifications', '0001_initial'),
    ]

    operations = [
        migrations.CreateModel(
            name='NostrPubkeyDevice',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('pubkey_hex', models.CharField(db_index=True, max_length=64)),
                ('wallet_hash', models.CharField(db_index=True, max_length=70)),
                ('multi_wallet_index', models.IntegerField(blank=True, null=True)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('last_active', models.DateTimeField(auto_now=True)),
                ('apns_device', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE, related_name='nostr_pubkeys', to='push_notifications.apnsdevice')),
                ('gcm_device', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE, related_name='nostr_pubkeys', to='push_notifications.gcmdevice')),
            ],
            options={
                'unique_together': {('pubkey_hex', 'gcm_device'), ('pubkey_hex', 'apns_device')},
            },
        ),
        migrations.AddIndex(
            model_name='nostrpubkeydevice',
            index=models.Index(fields=['pubkey_hex', 'wallet_hash'], name='nostr_pubke_pubkey_116898_idx'),
        ),
    ]