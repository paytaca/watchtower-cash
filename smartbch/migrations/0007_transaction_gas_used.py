# Generated by Django 3.0.14 on 2022-05-04 04:09

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('smartbch', '0006_tokencontract_image_url_source'),
    ]

    operations = [
        migrations.AddField(
            model_name='transaction',
            name='gas_used',
            field=models.IntegerField(blank=True, null=True),
        ),
    ]
