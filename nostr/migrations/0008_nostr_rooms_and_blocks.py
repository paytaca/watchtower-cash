from django.db import migrations, models
from django.contrib.postgres.fields import JSONField


class Migration(migrations.Migration):

    dependencies = [
        ('nostr', '0007_nostrpubkey_show_active_status'),
    ]

    operations = [
        migrations.CreateModel(
            name='NostrRoom',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('room_id', models.CharField(max_length=128)),
                ('wallet_hash', models.CharField(db_index=True, max_length=70)),
                ('type', models.CharField(max_length=10)),
                ('name', models.CharField(max_length=255)),
                ('members', JSONField(default=list)),
                ('subject', models.TextField(blank=True, null=True)),
                ('avatar', models.URLField(blank=True, null=True)),
                ('created_at', models.DateTimeField()),
                ('updated_at', models.DateTimeField()),
                ('archived', models.BooleanField(default=False)),
            ],
            options={
                'unique_together': {('wallet_hash', 'room_id')},
            },
        ),
        migrations.CreateModel(
            name='NostrBlockedContact',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('wallet_hash', models.CharField(db_index=True, max_length=70)),
                ('pub_key_hex', models.CharField(max_length=64)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
            ],
            options={
                'unique_together': {('wallet_hash', 'pub_key_hex')},
            },
        ),
        migrations.CreateModel(
            name='NostrBlockedGroup',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('wallet_hash', models.CharField(db_index=True, max_length=70)),
                ('room_id', models.CharField(max_length=128)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
            ],
            options={
                'unique_together': {('wallet_hash', 'room_id')},
            },
        ),
    ]
