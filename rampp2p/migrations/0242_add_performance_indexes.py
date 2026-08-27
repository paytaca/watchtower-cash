from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("rampp2p", "0241_status_order_created_index"),
    ]

    operations = [
        migrations.AddIndex(
            model_name="ordermember",
            index=models.Index(fields=["peer", "read_at"], name="rampp2p_om_peer_read_idx"),
        ),
        migrations.AddIndex(
            model_name="ordermember",
            index=models.Index(
                fields=["arbiter", "read_at"], name="rampp2p_om_arbiter_read_idx"
            ),
        ),
        migrations.AddIndex(
            model_name="order",
            index=models.Index(
                fields=["owner", "-created_at"], name="rampp2p_order_owner_ct_idx"
            ),
        ),
        migrations.AddIndex(
            model_name="order",
            index=models.Index(fields=["created_at"], name="rampp2p_order_created_at_idx"),
        ),
    ]
