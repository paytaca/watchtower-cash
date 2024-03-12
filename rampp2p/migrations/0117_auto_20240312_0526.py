# Generated by Django 3.0.14 on 2024-03-12 05:26

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('rampp2p', '0116_auto_20240312_0516'),
    ]

    operations = [
        migrations.AlterField(
            model_name='ad',
            name='appeal_cooldown_choice',
            field=models.IntegerField(choices=[(15, '15 minutes'), (30, '30 minutes'), (45, '45 minutes'), (60, '60 minutes')], default=60),
        ),
        migrations.AlterField(
            model_name='adsnapshot',
            name='appeal_cooldown_choice',
            field=models.IntegerField(choices=[(15, '15 minutes'), (30, '30 minutes'), (45, '45 minutes'), (60, '60 minutes')]),
        ),
    ]
