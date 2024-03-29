# Generated by Django 3.0.14 on 2023-06-23 06:07

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('rampp2p', '0048_auto_20230613_0643'),
    ]

    operations = [
        migrations.CreateModel(
            name='MarketPrice',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('currency_symbol', models.CharField(max_length=10, unique=True)),
                ('price', models.DecimalField(decimal_places=2, default=0, editable=False, max_digits=18)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('modified_at', models.DateTimeField(auto_now=True)),
            ],
        ),
    ]
