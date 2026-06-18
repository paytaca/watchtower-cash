# Generated manually

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('jpp', '0003_invoiceoutput_description'),
    ]

    operations = [
        migrations.AlterField(
            model_name='invoice',
            name='required_fee_per_byte',
            field=models.FloatField(default=1.0),
        ),
    ]
