from django.views.generic import TemplateView


class WalletHistoryExplorerView(TemplateView):
    template_name = "main/wallet_history_explorer.html"
