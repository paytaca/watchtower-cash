# Generated by Django 3.0.14 on 2022-05-02 01:38

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('smartbch', '0004_auto_20220330_0706'),
    ]

    operations = [
        migrations.AddField(
            model_name='tokencontract',
            name='image_url',
            field=models.URLField(blank=True, null=True),
        ),
    ]
