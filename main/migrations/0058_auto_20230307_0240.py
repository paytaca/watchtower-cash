# Generated by Django 3.0.14 on 2023-03-07 02:40

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('main', '0057_token_mint_amount'),
    ]

    operations = [
        migrations.AddField(
            model_name='token',
            name='capability',
            field=models.CharField(blank=True, choices=[('mutable', 'Mutable'), ('minting', 'Minting'), ('none', 'None')], max_length=30, null=True),
        ),
        migrations.AddField(
            model_name='token',
            name='commitment',
            field=models.CharField(blank=True, max_length=255, null=True),
        ),
        migrations.AddField(
            model_name='token',
            name='is_cashtoken',
            field=models.BooleanField(default=False),
        ),
        migrations.AlterField(
            model_name='token',
            name='tokenid',
            field=models.CharField(blank=True, db_index=True, max_length=70),
        ),
        migrations.AlterUniqueTogether(
            name='token',
            unique_together={('name', 'tokenid', 'is_cashtoken')},
        ),
    ]
