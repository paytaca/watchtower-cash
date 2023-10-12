# Generated by Django 3.0.14 on 2023-10-09 03:39

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('rampp2p', '0082_auto_20231002_0508'),
    ]

    operations = [
        migrations.RemoveField(
            model_name='image',
            name='message',
        ),
        migrations.RemoveField(
            model_name='message',
            name='chat',
        ),
        migrations.RemoveField(
            model_name='message',
            name='from_peer',
        ),
        migrations.AddField(
            model_name='paymenttype',
            name='format_string',
            field=models.CharField(max_length=100, null=True),
        ),
        migrations.DeleteModel(
            name='Chat',
        ),
        migrations.DeleteModel(
            name='Image',
        ),
        migrations.DeleteModel(
            name='Message',
        ),
    ]