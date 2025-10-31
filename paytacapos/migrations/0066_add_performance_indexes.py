# Generated manually for performance optimization
# This migration adds database indexes to improve POS transaction history query performance

from django.db import migrations, models


class Migration(migrations.Migration):
    # Disable atomic to allow CONCURRENTLY index creation
    atomic = False

    dependencies = [
        ('paytacapos', '0065_poswallethistory'),
        ('main', '0107_assetsetting_unlisted_list'),
    ]

    operations = [
        # Add composite index on PosWalletHistory for faster joins
        migrations.AddIndex(
            model_name='poswallethistory',
            index=models.Index(
                fields=['wallet_history', 'posid'],
                name='paytacapos_pwh_wh_posid_idx'
            ),
        ),
        
        # Add index on WalletHistory for POS queries with timestamp ordering
        # This is done via RunSQL to add a partial index (WHERE clause)
        # CONCURRENTLY prevents table locks during index creation
        migrations.RunSQL(
            sql="""
            CREATE INDEX CONCURRENTLY main_wallethistory_wallet_time_pos_idx 
            ON main_wallethistory (wallet_id, tx_timestamp DESC NULLS LAST, date_created DESC NULLS LAST)
            WHERE wallet_id IS NOT NULL;
            """,
            reverse_sql="DROP INDEX CONCURRENTLY IF EXISTS main_wallethistory_wallet_time_pos_idx;",
        ),
    ]

