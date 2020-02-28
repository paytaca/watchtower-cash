from django.contrib import admin
from main.models import Token, Transaction, SlpAddress, BlockHeight
from django.contrib.auth.models import User, Group
from django.utils.html import format_html
from main.tasks import blockheight, client_acknowledgement
admin.site.site_header = 'SPLNotify'

class TokenAdmin(admin.ModelAdmin):
    list_display = [
        'name',
        'tokenid',
        'target_address'
    ]

class BlockHeightAdmin(admin.ModelAdmin):
    actions = ['rescan_selected_blockheights']

    list_display = [
        'number',
        'transactions_count',
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
    actions = ['resend_unacknowledge_transactions']

    list_display = [
        'txid',
        'amount',
        'source',
        'blockheight_number',
        'token',
        'acknowledge',
        'created_datetime'
    ]

    def get_actions(self, request):
        actions = super().get_actions(request)
        if 'delete_selected' in actions:
            del actions['delete_selected']
        return actions
        
    def blockheight_number(self, obj):
        if obj.blockheight is not None:
            return obj.blockheight.number
        return '---' 

    def resend_unacknowledge_transactions(modeladmin, request, queryset):
        for trans in queryset.filter(acknowledge=False):
            client_acknowledgement.delay(trans.token.tokenid, trans.id)

class SlpAddressAdmin(admin.ModelAdmin):
    list_display = [
        'address',
    ]

admin.site.unregister(User)
admin.site.unregister(Group)
admin.site.register(Token, TokenAdmin)
admin.site.register(Transaction, TransactionAdmin)
admin.site.register(SlpAddress, SlpAddressAdmin)
admin.site.register(BlockHeight, BlockHeightAdmin)