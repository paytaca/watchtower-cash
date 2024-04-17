# Generated by Django 3.0.14 on 2024-04-13 13:40

from django.db import migrations, models

def hedge_to_short(apps, schema_editor):
    HedgePositionMetadata = apps.get_model("anyhedge", "HedgePositionMetadata")
    HedgePositionOffer = apps.get_model("anyhedge", "HedgePositionOffer")
    MutualRedemption = apps.get_model("anyhedge", "MutualRedemption")
    HedgePositionMetadata.objects.filter(position_taker="hedge").update(position_taker="short")
    HedgePositionOffer.objects.filter(position="hedge").update(position="short")
    MutualRedemption.objects.filter(initiator="hedge").update(initiator="short")

def short_to_hedge(apps, schema_editor):
    HedgePositionMetadata = apps.get_model("anyhedge", "HedgePositionMetadata")
    HedgePositionOffer = apps.get_model("anyhedge", "HedgePositionOffer")
    MutualRedemption = apps.get_model("anyhedge", "MutualRedemption")
    HedgePositionMetadata.objects.filter(position_taker="short").update(position_taker="hedge")
    HedgePositionOffer.objects.filter(position="short").update(position="hedge")
    MutualRedemption.objects.filter(initiator="short").update(initiator="hedge")


class Migration(migrations.Migration):

    dependencies = [
        ('anyhedge', '0012_oracle_active'),
    ]

    operations = [
        migrations.RenameField(
            model_name='hedgeposition',
            old_name='hedge_address',
            new_name='short_address',
        ),
        migrations.RenameField(
            model_name='hedgeposition',
            old_name='hedge_address_path',
            new_name='short_address_path',
        ),
        migrations.RenameField(
            model_name='hedgeposition',
            old_name='hedge_funding_proposal',
            new_name='short_funding_proposal',
        ),
        migrations.RenameField(
            model_name='hedgeposition',
            old_name='hedge_pubkey',
            new_name='short_pubkey',
        ),
        migrations.RenameField(
            model_name='hedgeposition',
            old_name='hedge_wallet_hash',
            new_name='short_wallet_hash',
        ),
        migrations.RenameField(
            model_name='hedgepositionmetadata',
            old_name='total_hedge_funding_sats',
            new_name='total_short_funding_sats',
        ),
        migrations.RenameField(
            model_name='hedgesettlement',
            old_name='hedge_satoshis',
            new_name='short_satoshis',
        ),
        migrations.RenameField(
            model_name='mutualredemption',
            old_name='hedge_satoshis',
            new_name='short_satoshis',
        ),
        migrations.RenameField(
            model_name='mutualredemption',
            old_name='hedge_schnorr_sig',
            new_name='short_schnorr_sig',
        ),
        migrations.RenameField(
            model_name='settlementservice',
            old_name='hedge_signature',
            new_name='short_signature',
        ),
        migrations.AlterField(
            model_name='hedgepositionmetadata',
            name='position_taker',
            field=models.CharField(blank=True, choices=[('short', 'short'), ('long', 'long')], max_length=5, null=True),
        ),
        migrations.AlterField(
            model_name='hedgepositionoffer',
            name='position',
            field=models.CharField(blank=True, choices=[('short', 'Short'), ('long', 'Long')], max_length=5, null=True),
        ),
        migrations.AlterField(
            model_name='mutualredemption',
            name='initiator',
            field=models.CharField(choices=[('short', 'short'), ('long', 'long')], default='short', max_length=5),
        ),
        migrations.RunPython(hedge_to_short, short_to_hedge),
    ]
