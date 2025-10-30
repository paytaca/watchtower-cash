# Generated manually for performance optimization
# This migration adds database indexes to improve query performance for the Ad listing API

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('rampp2p', '0233_ad_description'),
    ]

    operations = [
        # Add individual indexes on Ad model for frequently filtered fields
        migrations.AddIndex(
            model_name='ad',
            index=models.Index(fields=['deleted_at'], name='rampp2p_ad_deleted_at_idx'),
        ),
        migrations.AddIndex(
            model_name='ad',
            index=models.Index(fields=['is_public'], name='rampp2p_ad_is_public_idx'),
        ),
        migrations.AddIndex(
            model_name='ad',
            index=models.Index(fields=['price_type'], name='rampp2p_ad_price_type_idx'),
        ),
        migrations.AddIndex(
            model_name='ad',
            index=models.Index(fields=['appeal_cooldown_choice'], name='rampp2p_ad_appeal_cooldown_idx'),
        ),
        migrations.AddIndex(
            model_name='ad',
            index=models.Index(fields=['trade_limits_in_fiat'], name='rampp2p_ad_trade_limits_in_fiat_idx'),
        ),
        migrations.AddIndex(
            model_name='ad',
            index=models.Index(fields=['created_at'], name='rampp2p_ad_created_at_idx'),
        ),
        
        # Add indexes on trade amount fields
        migrations.AddIndex(
            model_name='ad',
            index=models.Index(fields=['trade_amount_sats'], name='rampp2p_ad_trade_amount_sats_idx'),
        ),
        migrations.AddIndex(
            model_name='ad',
            index=models.Index(fields=['trade_amount_fiat'], name='rampp2p_ad_trade_amount_fiat_idx'),
        ),
        
        # Add composite index for the most common query pattern
        # This covers: deleted_at, is_public, trade_type, fiat_currency_id
        migrations.AddIndex(
            model_name='ad',
            index=models.Index(
                fields=['deleted_at', 'is_public', 'trade_type', 'fiat_currency'],
                name='rampp2p_ad_common_query_idx'
            ),
        ),
        
        # Add composite index for trade amount filtering patterns
        migrations.AddIndex(
            model_name='ad',
            index=models.Index(
                fields=['trade_limits_in_fiat', 'trade_amount_sats'],
                name='rampp2p_ad_trade_sats_idx'
            ),
        ),
        migrations.AddIndex(
            model_name='ad',
            index=models.Index(
                fields=['trade_limits_in_fiat', 'trade_amount_fiat'],
                name='rampp2p_ad_trade_fiat_idx'
            ),
        ),
        
        # Add composite index for public ads filtering with ordering
        migrations.AddIndex(
            model_name='ad',
            index=models.Index(
                fields=['is_public', 'deleted_at', 'created_at'],
                name='rampp2p_ad_public_listing_idx'
            ),
        ),
        
        # Optimize OrderFeedback for rating calculations
        # This helps with the subquery in priority ordering
        migrations.AddIndex(
            model_name='orderfeedback',
            index=models.Index(
                fields=['to_peer', 'rating'],
                name='rampp2p_feedback_rating_idx'
            ),
        ),
        
        # Optimize Order model for trade count calculations
        # Note: order.owner already has FK index, but we add composite for better performance
        migrations.AddIndex(
            model_name='order',
            index=models.Index(
                fields=['ad_snapshot'],
                name='rampp2p_order_ad_snapshot_idx'
            ),
        ),
    ]

