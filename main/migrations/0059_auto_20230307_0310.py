# Generated by Django 3.0.14 on 2023-03-07 03:10

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('main', '0058_auto_20230307_0240'),
    ]

    operations = [
        migrations.AlterField(
            model_name='token',
            name='tokenid',
            field=models.CharField(blank=True, db_index=True, max_length=70, unique=True),
        ),
        migrations.AlterUniqueTogether(
            name='token',
            unique_together={('name', 'tokenid')},
        ),
    ]
