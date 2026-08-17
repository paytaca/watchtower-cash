from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('main', '0128_auto_20260623_0728'),
    ]

    operations = [
        migrations.CreateModel(
            name='WalletActivity',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('activity_date', models.DateField(db_index=True)),
                ('kind', models.CharField(choices=[('transaction-send', 'Transaction Send'), ('app-opening', 'App Opening')], db_index=True, max_length=32)),
                ('amount', models.BigIntegerField(blank=True, null=True)),
                ('date_created', models.DateTimeField(auto_now_add=True)),
                ('history', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='activities', to='main.wallethistory')),
                ('wallet', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='activities', to='main.wallet')),
            ],
            options={
                'verbose_name': 'Wallet Activity',
                'verbose_name_plural': 'Wallet Activities',
                'ordering': ['-activity_date', '-date_created'],
                'constraints': [
                    models.UniqueConstraint(fields=['wallet', 'history', 'kind', 'activity_date'], name='unique_wallet_activity_wallet_history'),
                ],
            },
        ),
    ]