# Generated by Django 3.0.14 on 2023-07-19 01:32

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('paytacagifts', '0002_auto_20230717_1812'),
    ]

    operations = [
        migrations.AlterModelOptions(
            name='gift',
            options={'ordering': ['-date_created', '-date_funded']},
        ),
        migrations.AlterField(
            model_name='gift',
            name='address',
            field=models.CharField(db_index=True, max_length=64),
        ),
        migrations.AlterField(
            model_name='gift',
            name='gift_code_hash',
            field=models.CharField(max_length=70, unique=True),
        ),
        migrations.AddIndex(
            model_name='gift',
            index=models.Index(fields=['gift_code_hash'], name='paytacagift_gift_co_a644b2_idx'),
        ),
        migrations.AddIndex(
            model_name='gift',
            index=models.Index(fields=['date_funded'], name='paytacagift_date_fu_ebb49f_idx'),
        ),
        migrations.AddIndex(
            model_name='gift',
            index=models.Index(fields=['date_claimed'], name='paytacagift_date_cl_31ba5d_idx'),
        ),
    ]
