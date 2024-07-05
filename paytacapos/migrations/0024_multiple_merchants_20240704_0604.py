# Generated by Django 3.0.14 on 2024-07-04 06:04

from django.db import migrations, models
import django.db.models.deletion

# this is manually added
def populate_pos_device_merchant(apps, schema_editor):
    PosDevice = apps.get_model("paytacapos", "PosDevice")
    Merchant = apps.get_model("paytacapos", "Merchant")

    subquery = Merchant.objects \
        .filter(wallet_hash=models.OuterRef("wallet_hash")) \
        .order_by("id").values("id")[:1]

    PosDevice.objects.filter(merchant__isnull=True).update(merchant_id=subquery)



class Migration(migrations.Migration):

    dependencies = [
        ('paytacapos', '0023_auto_20240703_1615'),
    ]

    operations = [
        migrations.AddField(
            model_name='posdevice',
            name='merchant',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name='devices', to='paytacapos.Merchant'),
        ),
        migrations.RunPython(populate_pos_device_merchant, migrations.RunPython.noop),
        migrations.AlterField(
            model_name='merchant',
            name='wallet_hash',
            field=models.CharField(db_index=True, max_length=75),
        ),
    ]