# Generated by Django 3.0.14 on 2022-11-22 07:40

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('paytacapos', '0002_location_merchant'),
    ]

    operations = [
        migrations.CreateModel(
            name='Branch',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('name', models.CharField(max_length=75)),
                ('location', models.OneToOneField(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='branch', to='paytacapos.Location')),
                ('merchant', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='branches', to='paytacapos.Merchant')),
            ],
        ),
        migrations.AddField(
            model_name='posdevice',
            name='branch',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='devices', to='paytacapos.Branch'),
        ),
    ]
