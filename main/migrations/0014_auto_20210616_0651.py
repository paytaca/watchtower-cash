# Generated by Django 3.0.14 on 2021-06-16 06:51

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('main', '0013_auto_20210615_2353'),
    ]

    operations = [
        migrations.CreateModel(
            name='Wallet',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('wallet_hash', models.CharField(db_index=True, max_length=200)),
                ('derivation_path', models.CharField(max_length=100)),
            ],
        ),
        migrations.RemoveField(
            model_name='bchaddress',
            name='scanned',
        ),
        migrations.AlterField(
            model_name='bchaddress',
            name='address',
            field=models.CharField(db_index=True, max_length=70, unique=True),
        ),
        migrations.AlterField(
            model_name='slpaddress',
            name='address',
            field=models.CharField(db_index=True, max_length=70, unique=True),
        ),
        migrations.CreateModel(
            name='Address',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('address', models.CharField(db_index=True, max_length=70, unique=True)),
                ('wallet_index', models.IntegerField(blank=True, null=True)),
                ('wallet', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE, related_name='addresses', to='main.Wallet')),
            ],
        ),
        migrations.AddField(
            model_name='subscription',
            name='address',
            field=models.ForeignKey(default='', on_delete=django.db.models.deletion.CASCADE, related_name='subscriptions', to='main.Address'),
            preserve_default=False,
        ),
    ]
