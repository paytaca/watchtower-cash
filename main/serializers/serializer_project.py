from rest_framework import serializers
from django.db.models import Count, F
from main.models import Project, WalletHistory, TransactionMetaAttribute
from datetime import datetime


def get_transactions_by_attributes(project_id, attribute_value, **filters):
    meta_attributes = TransactionMetaAttribute.objects.filter(value=attribute_value)
    txids_with_attrs = meta_attributes.distinct('txid').values_list('txid', flat=True)
    txids_with_attrs = list(txids_with_attrs)
    transactions = WalletHistory.objects.filter(
        wallet__project_id=project_id,
        txid__in=txids_with_attrs
    )
    
    wallet_hash = filters.get('wallet_hash', None)
    basis_date = filters.get('basis_date', None)
    if wallet_hash: transactions = transactions.filter(wallet__wallet_hash=wallet_hash)
    if basis_date: transactions = transactions.filter(date_created__gte=basis_date)
    return transactions


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
        request = self.context.get('request')
        wallet_hash = None
        basis_date = None
        filters = {}

        if request:
            query_params = request.query_params
            wallet_hash = query_params.get('wallet_hash', None)
            basis_date = query_params.get('basis_date', None)
            
        transactions = WalletHistory.objects.filter(wallet__project_id=obj.id)
        if wallet_hash:
            filters['wallet_hash'] = wallet_hash
            transactions = transactions.filter(wallet__wallet_hash=wallet_hash)
        if basis_date:
            dt = datetime.fromisoformat(basis_date)
            filters['basis_date'] = dt
            transactions = transactions.filter(date_created__gte=dt)

        incoming_txns = transactions.filter(record_type='incoming')
        outgoing_txns = transactions.filter(record_type='outgoing')
        txns_count = {
            'total': transactions.count(),
            'incoming': incoming_txns.count(),
            'outgoing': outgoing_txns.count(),
        }
        wallet_txns_count = transactions.values(wallet_hash=F('wallet__wallet_hash'))
        wallet_txns_count = wallet_txns_count.annotate(count=Count('id'))

        # PurelyPeer specific stats
        purelypeer_project_ids = [
            '526ed3fd-8ce0-4960-8c2a-3faca848d180',
            '74fa1369-0a50-4baf-be9e-f8da7fcda6f5',
        ]
        if str(obj.id) in purelypeer_project_ids:
            cashdrop_collect_txns = get_transactions_by_attributes(obj.id, 'Collected CashDrop BCH', **filters)
            quest_nft_collect_txns = get_transactions_by_attributes(obj.id, 'Collected CashDrop NFT', **filters)
            quest_payment_txns = get_transactions_by_attributes(obj.id, 'Quest Payment', **filters)
            vault_collect_txns = get_transactions_by_attributes(obj.id, 'Collected Vault BCH', **filters)
            vault_payment_txns = get_transactions_by_attributes(obj.id, 'Vault Payment', **filters)
            
            other_txns_count = {
                'cashdrop_collect': cashdrop_collect_txns.count(),
                'quest_nft_collect': quest_nft_collect_txns.count(),
                'quest_payment': quest_payment_txns.count(),
                'vault_collect': vault_collect_txns.count(),
                'vault_payment': vault_payment_txns.count(),
            }
            txns_count = {
                'wallet_txns_count': wallet_txns_count,
                **txns_count,
                **other_txns_count
            }

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