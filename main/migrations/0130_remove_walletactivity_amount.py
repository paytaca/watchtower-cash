from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('main', '0129_walletactivity'),
    ]

    operations = [
        migrations.RemoveField(
            model_name='walletactivity',
            name='amount',
        ),
    ]