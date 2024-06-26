# Generated by Django 3.0.14 on 2024-04-29 05:32

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('rampp2p', '0144_auto_20240429_0511'),
    ]

    operations = [
        migrations.AlterUniqueTogether(
            name='ordermember',
            unique_together=set(),
        ),
        migrations.AddConstraint(
            model_name='ordermember',
            constraint=models.UniqueConstraint(condition=models.Q(peer__isnull=False), fields=('type', 'peer', 'order'), name='unique_peer_order'),
        ),
        migrations.AddConstraint(
            model_name='ordermember',
            constraint=models.UniqueConstraint(condition=models.Q(arbiter__isnull=False), fields=('type', 'arbiter', 'order'), name='unique_arbiter_order'),
        ),
    ]
