# Generated by Django 3.0.14 on 2024-06-18 07:31

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('rampp2p', '0163_auto_20240618_0334'),
    ]

    operations = [
        migrations.AlterField(
            model_name='ordermember',
            name='arbiter',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE, related_name='order_members', to='rampp2p.Arbiter'),
        ),
        migrations.AlterField(
            model_name='ordermember',
            name='peer',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE, related_name='order_members', to='rampp2p.Peer'),
        ),
    ]
