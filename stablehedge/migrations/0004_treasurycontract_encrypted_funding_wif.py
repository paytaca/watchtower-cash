# Generated by Django 3.0.14 on 2024-10-28 08:59

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('stablehedge', '0003_treasurycontract'),
    ]

    operations = [
        migrations.AddField(
            model_name='treasurycontract',
            name='encrypted_funding_wif',
            field=models.CharField(blank=True, max_length=200, null=True, unique=True, help_text="Add prefix 'bch-wif:', if data is not encrypted"),
        ),
    ]
