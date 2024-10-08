# Generated by Django 3.0.14 on 2024-08-22 05:16

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('rampp2p', '0180_auto_20240822_0259'),
    ]

    operations = [
        migrations.RemoveField(
            model_name='peer',
            name='is_cashin_blacklisted',
        ),
        migrations.RemoveField(
            model_name='peer',
            name='is_cashin_whitelisted',
        ),
        migrations.AddField(
            model_name='fiatcurrency',
            name='cashin_blacklist',
            field=models.ManyToManyField(related_name='cashin_currency_blacklist', to='rampp2p.Peer'),
        ),
        migrations.AddField(
            model_name='fiatcurrency',
            name='cashin_whitelist',
            field=models.ManyToManyField(related_name='cashin_currency_whitelist', to='rampp2p.Peer'),
        ),
        migrations.AlterField(
            model_name='fiatcurrency',
            name='name',
            field=models.CharField(db_index=True, max_length=100),
        ),
    ]
