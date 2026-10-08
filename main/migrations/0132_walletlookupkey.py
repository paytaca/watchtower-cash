from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('main', '0131_auto_20260825_0143'),
    ]

    operations = [
        migrations.CreateModel(
            name='WalletLookupKey',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('key_hash', models.CharField(db_index=True, max_length=64, unique=True)),
                ('label', models.CharField(blank=True, default='', max_length=100)),
                ('date_created', models.DateTimeField(auto_now_add=True)),
                ('last_used_at', models.DateTimeField(blank=True, null=True)),
                ('wallet', models.OneToOneField(on_delete=django.db.models.deletion.CASCADE, related_name='lookup_key', to='main.wallet')),
            ],
            options={
                'verbose_name': 'Wallet Lookup Key',
                'verbose_name_plural': 'Wallet Lookup Keys',
                'ordering': ['-date_created'],
            },
        ),
    ]
