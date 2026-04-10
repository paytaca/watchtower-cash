from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [
        ("rampp2p", "0234_add_performance_indexes"),
    ]

    operations = [
        migrations.AlterUniqueTogether(
            name="orderpayment",
            unique_together={("order", "payment_method")},
        ),
    ]
