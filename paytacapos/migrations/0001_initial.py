# Generated by Django 3.0.14 on 2022-10-13 04:53

from django.db import migrations, models


class Migration(migrations.Migration):

    initial = True

    dependencies = [
    ]

    operations = [
        migrations.CreateModel(
            name='PosDevice',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('posid', models.IntegerField()),
                ('wallet_hash', models.CharField(max_length=70)),
                ('name', models.CharField(blank=True, max_length=100, null=True)),
            ],
            options={
                'unique_together': {('posid', 'wallet_hash')},
            },
        ),
    ]