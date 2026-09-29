from django import forms
from django.shortcuts import render

from main.utils.wallet_balance_history import (
    get_wallet_balance_history, DEFAULT_PER_PAGE, DEFAULT_TIMEZONE)


FIAT_CURRENCY_CHOICES = [
    ('USD', 'USD - US Dollar'),
    ('EUR', 'EUR - Euro'),
    ('GBP', 'GBP - British Pound'),
    ('JPY', 'JPY - Japanese Yen'),
    ('AUD', 'AUD - Australian Dollar'),
    ('CAD', 'CAD - Canadian Dollar'),
    ('CHF', 'CHF - Swiss Franc'),
    ('CNY', 'CNY - Chinese Yuan'),
    ('HKD', 'HKD - Hong Kong Dollar'),
    ('NZD', 'NZD - New Zealand Dollar'),
    ('SGD', 'SGD - Singapore Dollar'),
    ('PHP', 'PHP - Philippine Peso'),
]

TIMEZONE_CHOICES = [
    ('Asia/Manila', 'Asia/Manila (PHT)'),
    ('UTC', 'UTC'),
    ('Asia/Singapore', 'Asia/Singapore'),
    ('Asia/Hong_Kong', 'Asia/Hong Kong'),
    ('Asia/Tokyo', 'Asia/Tokyo'),
    ('Europe/London', 'Europe/London'),
    ('Europe/Berlin', 'Europe/Berlin'),
    ('America/New_York', 'America/New York'),
    ('America/Chicago', 'America/Chicago'),
    ('America/Los_Angeles', 'America/Los Angeles'),
    ('Australia/Sydney', 'Australia/Sydney'),
]


class WalletBalanceHistoryForm(forms.Form):
    wallet_hash = forms.CharField(max_length=70, required=True)
    fiat_currency = forms.ChoiceField(
        choices=FIAT_CURRENCY_CHOICES,
        initial='PHP',
        required=False,
    )
    date_timezone = forms.ChoiceField(
        choices=TIMEZONE_CHOICES,
        initial=DEFAULT_TIMEZONE,
        required=False,
    )
    page = forms.IntegerField(required=False, min_value=1)


def wallet_balance_history_view(request):
    form = WalletBalanceHistoryForm(
        initial={'fiat_currency': 'PHP', 'date_timezone': DEFAULT_TIMEZONE})
    wallet_data = None
    error = None
    submitted = False

    if request.method == 'GET' and request.GET.get('wallet_hash'):
        form = WalletBalanceHistoryForm(request.GET)
        if form.is_valid():
            submitted = True
            wallet_hash = form.cleaned_data['wallet_hash'].strip()
            fiat_currency = form.cleaned_data.get('fiat_currency') or 'PHP'
            date_timezone = form.cleaned_data.get('date_timezone') or DEFAULT_TIMEZONE
            page = form.cleaned_data.get('page') or 1

            wallet_data, error = get_wallet_balance_history(
                wallet_hash,
                fiat_currency=fiat_currency,
                page=page,
                per_page=DEFAULT_PER_PAGE,
                date_timezone=date_timezone,
            )

    context = {
        'form': form,
        'wallet_data': wallet_data,
        'error': error,
        'submitted': submitted,
        'fiat_choices': FIAT_CURRENCY_CHOICES,
        'timezone_choices': TIMEZONE_CHOICES,
    }
    return render(request, 'main/wallet_balance_history.html', context)
