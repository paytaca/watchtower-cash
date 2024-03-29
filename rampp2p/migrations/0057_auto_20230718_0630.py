# Generated by Django 3.0.14 on 2023-07-18 06:30

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('rampp2p', '0056_auto_20230706_0424'),
    ]

    operations = [
        migrations.AlterField(
            model_name='status',
            name='order',
            field=models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to='rampp2p.Order'),
        ),
        migrations.AlterField(
            model_name='status',
            name='status',
            field=models.CharField(choices=[('SBM', 'Submitted'), ('ESCRW_PN', 'Escrow Pending'), ('ESCRW', 'Escrowed'), ('PD_PN', 'Paid Pending'), ('PD', 'Paid'), ('RLS_APL', 'Appealed for Release'), ('RFN_APL', 'Appealed for Refund'), ('RLS_PN', 'Release Pending'), ('RLS', 'Released'), ('RFN_PN', 'Refund Pending'), ('RFN', 'Refunded'), ('CNCL', 'Canceled')], max_length=10),
        ),
    ]
