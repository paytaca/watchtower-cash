# Generated by Django 3.0.14 on 2023-04-17 02:08

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('rampp2p', '0023_auto_20230414_0410'),
    ]

    operations = [
        migrations.AlterField(
            model_name='status',
            name='status',
            field=models.CharField(choices=[('SBM', 'Submitted'), ('CNF', 'Confirmed'), ('PD_PN', 'Paid Pending'), ('PD', 'Paid'), ('CNCL_APL', 'Appealed for Cancel'), ('RLS_APL', 'Appealed for Release'), ('RFN_APL', 'Appealed for Refund'), ('RLS', 'Released'), ('RFN', 'Refunded'), ('CNCL', 'Canceled')], editable=False, max_length=10),
        ),
    ]
