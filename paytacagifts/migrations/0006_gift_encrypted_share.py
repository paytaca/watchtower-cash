# Generated by Django 3.0.14 on 2024-09-08 02:51

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('paytacagifts', '0005_auto_20240416_0213'),
    ]

    operations = [
        migrations.AddField(
            model_name='gift',
            name='encrypted_share',
            field=models.CharField(default='', max_length=255),
            preserve_default=False,
        ),
    ]
