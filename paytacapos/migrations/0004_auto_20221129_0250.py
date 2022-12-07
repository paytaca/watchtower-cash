# Generated by Django 3.0.14 on 2022-11-29 02:50

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('paytacapos', '0003_auto_20221122_0740'),
    ]

    operations = [
        migrations.CreateModel(
            name='LinkedDeviceInfo',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('link_code', models.CharField(max_length=100, unique=True)),
                ('device_id', models.CharField(blank=True, max_length=50, null=True)),
                ('name', models.CharField(blank=True, max_length=50, null=True)),
                ('device_model', models.CharField(blank=True, max_length=50, null=True)),
                ('os', models.CharField(blank=True, max_length=15, null=True)),
                ('is_suspended', models.BooleanField(default=False)),
            ],
        ),
        migrations.AlterModelOptions(
            name='branch',
            options={'verbose_name_plural': 'branches'},
        ),
        migrations.AddField(
            model_name='posdevice',
            name='linked_device',
            field=models.OneToOneField(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='pos_device', to='paytacapos.LinkedDeviceInfo'),
        ),
    ]
