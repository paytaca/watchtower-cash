# Generated by Django 3.0.14 on 2023-04-14 04:10

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('rampp2p', '0022_auto_20230414_0218'),
    ]

    operations = [
        migrations.AlterField(
            model_name='appeal',
            name='type',
            field=models.CharField(choices=[('CNCL', 'Cancel'), ('RLS', 'Release'), ('RFN', 'Refund')], editable=False, max_length=10),
        ),
    ]
