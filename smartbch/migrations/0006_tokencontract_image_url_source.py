# Generated by Django 3.0.14 on 2022-05-02 02:58

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('smartbch', '0005_tokencontract_image_url'),
    ]

    operations = [
        migrations.AddField(
            model_name='tokencontract',
            name='image_url_source',
            field=models.CharField(blank=True, max_length=20, null=True),
        ),
    ]
