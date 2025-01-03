# Generated by Django 3.0.14 on 2024-12-03 02:20

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('rampp2p', '0223_merge_20241203_0220'),
    ]

    operations = [
        migrations.CreateModel(
            name='FeatureToggle',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('feature_name', models.CharField(max_length=100, unique=True)),
                ('is_enabled', models.BooleanField(default=False)),
            ],
        ),
    ]
