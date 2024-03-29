# Generated by Django 3.0.14 on 2023-04-13 09:58

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('rampp2p', '0019_appeal'),
    ]

    operations = [
        migrations.AlterField(
            model_name='status',
            name='status',
            field=models.CharField(choices=[('SBM', 'Submitted'), ('CNF', 'Confirmed'), ('PD', 'Paid'), ('APL', 'Appealed'), ('RLS', 'Released'), ('RFN', 'Refunded'), ('CNCL', 'Canceled')], editable=False, max_length=5, unique=True),
        ),
    ]
