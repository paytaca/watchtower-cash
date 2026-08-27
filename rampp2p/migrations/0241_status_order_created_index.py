from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('rampp2p', '0240_remove_report_unique_together'),
    ]

    operations = [
        migrations.AddIndex(
            model_name='status',
            index=models.Index(
                fields=['order', '-created_at'],
                name='rampp2p_status_order_created_idx',
            ),
        ),
    ]