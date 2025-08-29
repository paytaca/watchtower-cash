from rest_framework import serializers

from main.models import Project, WalletHistory, TransactionMetaAttribute


def get_transactions_by_attributes(project, attribute_value):
    wallet_hashes = project.wallets.values('wallet_hash').distinct('wallet_hash')
    meta_attributes = TransactionMetaAttribute.objects.filter(wallet_hash__in=wallet_hashes)
    meta_attributes = meta_attributes.filter(value=attribute_value)
    wallet_txids_with_attrs = meta_attributes.values('txid').distinct('txid')
    transactions = WalletHistory.objects.filter(wallet__project_id=project.id)
    return transactions.filter(txid__in=wallet_txids_with_attrs)


class ProjectSerializer(serializers.ModelSerializer):
    stats = serializers.SerializerMethodField()


    class Meta:
        model = Project
        fields = (
            'id',
            'name',
            'date_created',
            'transactions_count',
            'wallets_count',
            'addresses_count',
            'stats',
        )

    
    def get_stats(self, obj):
        transactions = WalletHistory.objects.filter(wallet__project_id=obj.id)
        incoming_txns = transactions.filter(record_type='incoming')
        outgoing_txns = transactions.filter(record_type='outgoing')
        txns_count = {
            'total': obj.transactions_count,
            'incoming': incoming_txns.count(),
            'outgoing': outgoing_txns.count(),
        }

        # PurelyPeer specific stats
        purelypeer_project_ids = [
            '526ed3fd-8ce0-4960-8c2a-3faca848d180',
            '74fa1369-0a50-4baf-be9e-f8da7fcda6f5',
        ]
        if obj.id in purelypeer_project_ids:
            cashdrop_collect_txns = get_transactions_by_attributes(obj, 'Collected CashDrop BCH')
            quest_nft_collect_txns = get_transactions_by_attributes(obj, 'Collected CashDrop NFT')
            quest_payment_txns = get_transactions_by_attributes(obj, 'Quest Payment')
            vault_txns = transactions.filter(address__address__istartswith='bitcoincash:p')
            other_txns_count = {
                'cashdrop_collect': cashdrop_collect_txns.count(),
                'quest_nft_collect': quest_nft_collect_txns.count(),
                'quest_payment': quest_payment_txns,
                'vault_payment': vault_txns.filter(record_type='incoming').count(),
                'vault_collect': vault_txns.filter(record_type='outgoing').count(),
            }
            txns_count = { **txns_count, **other_txns_count }

        return {
            'transactions': txns_count,
        }


class PaginatedProjectLeaderboardSerializer(serializers.Serializer):
    page = serializers.IntegerField()
    page_size = serializers.IntegerField()
    num_pages = serializers.IntegerField()
    has_next = serializers.BooleanField()    
    leaderboard = ProjectSerializer(many=True)


class ProjectWalletsSerializer(serializers.Serializer):
    wallets = serializers.ListField(
        child=serializers.CharField(
            help_text="List of wallet hashes that belong to the project"
        )
    )