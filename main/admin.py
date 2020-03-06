from django.contrib import admin
from main.models import Token, Transaction, SlpAddress, BlockHeight, Subscriber
from django.contrib.auth.models import User, Group
from django.utils.html import format_html
from main.tasks import blockheight, client_acknowledgement
admin.site.site_header = 'SPLNotify'

class TokenAdmin(admin.ModelAdmin):
    list_display = [
        'name',
        'tokenid',
        'target_address',
    ]

    def get_queryset(self, request): 
        # For Django < 1.6, override queryset instead of get_queryset
        qs = super(TokenAdmin, self).get_queryset(request) 
        if request.user.is_superuser:
            return qs
        return qs.filter(subscriber__user=request.user)

class BlockHeightAdmin(admin.ModelAdmin):
    actions = ['rescan_selected_blockheights']
    ordering = ('-number',)

    list_display = [
        'number',
        '_slp_transactions',
        'created_datetime',
        'updated_datetime',
        'processed',
        '_actions'
    ]

    


    def rescan_selected_blockheights(modeladmin, request, queryset):
        for trans in queryset:
            blockheight.delay(trans.id)
            BlockHeight.objects.filter(id=trans.id).update(processed=False)

    def get_actions(self, request):
        actions = super().get_actions(request)
        if 'delete_selected' in actions:
            del actions['delete_selected']
        return actions

    def _slp_transactions(self, obj):
        return obj.transactions_count

    def _actions(self, obj):
        if obj.processed:
            return format_html(
                    f"""<a class="button"
                    href="/main/blockheight?rescan={obj.id}"
                    style="background-color: transparent;padding:0px;"><img src='/static/admin/img/search.svg'></img></a>"""
                )
        else:
            return format_html('<span style="color:blue"> Scanning...</span>')
    
    def changelist_view(self, request, extra_context=None):
        self.param = request.GET.get('rescan', None)
        if self.param:
            blockheight.delay(self.param)
            BlockHeight.objects.filter(id=self.param).update(processed=False)
        return super(BlockHeightAdmin,self).changelist_view(request, extra_context=extra_context)


class TransactionAdmin(admin.ModelAdmin):
    search_fields = ['token__name', 'source', 'txid']

    actions = ['resend_unacknowledge_transactions']

    list_display = [
        '_txid',
        'amount',
        'source',
        'blockheight_number',
        'token',
        'acknowledge',
        'created_datetime'
    ]

    def _txid(self, obj):
        url = f'https://explorer.bitcoin.com/bch/tx/{obj.txid}'
        return format_html(
            f"""<a class="button"
            target="_blank" 
            href="{url}"
            style="background-color:transparent;
            padding:0px;
            color:#447e9b;
            text-decoration:None;
            font-weight:bold;">{obj.txid}</a>"""
        )

    def get_actions(self, request):
        actions = super().get_actions(request)
        if 'delete_selected' in actions:
            del actions['delete_selected']
        return actions
        
    def blockheight_number(self, obj):
        if obj.blockheight is not None:
            return obj.blockheight.number
        return f'----'

    def resend_unacknowledge_transactions(modeladmin, request, queryset):
        for trans in queryset.filter(acknowledge=False):
            client_acknowledgement.delay(trans.token.tokenid, trans.id)

    def get_queryset(self, request): 
        # For Django < 1.6, override queryset instead of get_queryset
        qs = super(TransactionAdmin, self).get_queryset(request) 
        if request.user.is_superuser:
            return qs
        subscriber = Subscriber.objects.filter(user=request.user)
        if subscriber.exists():
            obj = subscriber.first()
            token_ids = obj.token.values_list('id',flat=True).distinct()
            return Transaction.objects.filter(token__id__in=token_ids)
        else:
            return qs.filter(id=0)

class SlpAddressAdmin(admin.ModelAdmin):
    list_display = [
        'address',
    ]


class SubscriberAdmin(admin.ModelAdmin):
    list_display = [
        'user',
    ]

# admin.site.register(User)
# admin.site.register(Group)
admin.site.register(Token, TokenAdmin)
admin.site.register(Transaction, TransactionAdmin)
admin.site.register(SlpAddress, SlpAddressAdmin)
admin.site.register(BlockHeight, BlockHeightAdmin)
admin.site.register(Subscriber, SubscriberAdmin)