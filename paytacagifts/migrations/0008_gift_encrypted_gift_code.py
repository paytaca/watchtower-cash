# Generated migration for encrypted_gift_code field

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('paytacagifts', '0007_auto_20240908_0726'),
    ]

    operations = [
        migrations.AddField(
            model_name='gift',
            name='encrypted_gift_code',
            field=models.TextField(blank=True, default=''),
        ),
    ]

