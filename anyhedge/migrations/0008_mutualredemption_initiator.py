# Generated by Django 3.0.14 on 2023-01-26 06:20

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('anyhedge', '0007_delete_longaccount'),
    ]

    operations = [
        migrations.AddField(
            model_name='mutualredemption',
            name='initiator',
            field=models.CharField(choices=[('hedge', 'hedge'), ('long', 'long')], default='hedge', max_length=5),
        ),
    ]