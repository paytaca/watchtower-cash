from django import forms
from django.core.exceptions import ValidationError
from decimal import Decimal
from .models import *

class TradeFeeForm(forms.ModelForm):
    def __init__(self, *args, **kwargs):
        super(TradeFeeForm, self).__init__(*args, **kwargs)
        if not self.fields['fixed_value'].initial:
            self.fields['fixed_value'].initial = TradeFee._meta.get_field('fixed_value').default
        if not self.fields['floating_value'].initial:
            self.fields['floating_value'].initial = TradeFee._meta.get_field('floating_value').default

    def validate_fixed_value(value): 
        if value < Decimal('1000'):
            raise ValidationError('The fixed service fee amount must be at least 1000 satoshis.')
    
    def validate_floating_value(value):
        if value < Decimal('0.5'):
            raise ValidationError('The service fee percentage must be at least 0.5')

    fixed_value = forms.DecimalField(
        required=True,
        help_text='Enter the fixed fee amount in satoshis',
        validators=[validate_fixed_value]
    )
    floating_value = forms.DecimalField(
        required=True,
        help_text='Enter the fee as a percentage of the trade amount (e.g., 5 for 5%)',
        validators=[validate_floating_value]
    )

    class Meta:
        model = TradeFee
        fields = '__all__'

class FiatCurrencyForm(forms.ModelForm):
    cashin_blacklist = forms.ModelMultipleChoiceField(
        queryset=Peer.objects.all(),
        help_text='Peers not allowed to receive cash-in orders in this currency. If whitelist is not empty, this list is ignored.',
        required=False
    )
    cashin_whitelist = forms.ModelMultipleChoiceField(
        queryset=Peer.objects.all(),
        help_text='Peers allowed to receive cash-in orders in this currency. Blacklist is ignored if this list is not empty.',
        required=False
    )
    cashin_presets = forms.CharField(
        widget=forms.Textarea,
        required=False,
        help_text='Enter a comma-separated list of integers'
    )

    class Meta:
        model = FiatCurrency
        fields = '__all__'

    def clean_cashin_presets(self):
        data = self.cleaned_data['cashin_presets']
        if data:
            int_values = data.split(',')
            try:
                presets = [int(value.strip()) for value in int_values]
            except ValueError:
                raise forms.ValidationError("Enter a comma-separated list of integers")
            return ','.join(map(str, presets))
        return data
    
class CryptoCurrencyForm(forms.ModelForm):
    cashin_presets = forms.CharField(
        widget=forms.Textarea,
        required=False,
        help_text='Enter a comma-separated list of integers'
    )

    class Meta:
        model = CryptoCurrency
        fields = '__all__'

    def clean_cashin_presets(self):
        data = self.cleaned_data['cashin_presets']
        if data:
            int_values = data.split(',')
            try:
                presets = [int(value.strip()) for value in int_values]
            except ValueError:
                raise forms.ValidationError("Enter a comma-separated list of integers")
            return ','.join(map(str, presets))
        return data