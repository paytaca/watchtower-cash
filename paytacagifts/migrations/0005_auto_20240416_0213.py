# Generated by Django 3.0.14 on 2024-04-16 02:13

from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('paytacagifts', '0004_auto_20240414_0652'),
    ]

    operations = [
        migrations.AlterModelOptions(
            name='campaign',
            options={'ordering': ['-date_created']},
        ),
        migrations.AlterModelOptions(
            name='claim',
            options={'ordering': ['-date_created']},
        ),
        migrations.AlterModelOptions(
            name='wallet',
            options={'ordering': ['-date_created']},
        ),
    ]
