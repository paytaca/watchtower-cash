# Generated by Django 3.0.14 on 2025-01-20 03:01

from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('rampp2p', '0229_featurecontrol'),
    ]

    operations = [
        migrations.RenameModel(
            old_name='MarketRate',
            new_name='MarketPrice',
        ),
        migrations.RenameModel(
            old_name='Feedback',
            new_name='OrderFeedback',
        ),
        migrations.DeleteModel(
            name='IdentifierFormat',
        ),
    ]
