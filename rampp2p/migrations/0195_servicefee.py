# Generated by Django 3.0.14 on 2024-11-13 09:35

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('rampp2p', '0194_merge_20241017_0634'),
    ]

    operations = [
        migrations.CreateModel(
            name='ServiceFee',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('type', models.CharField(choices=[('fixed', 'Fixed'), ('floating', 'Floating')], max_length=8)),
                ('fixed_value', models.DecimalField(blank=True, decimal_places=8, default=1e-05, max_digits=18)),
                ('floating_value', models.DecimalField(blank=True, decimal_places=8, default=0.5, max_digits=18)),
                ('updated_at', models.DateTimeField(auto_now=True)),
            ],
        ),
    ]
