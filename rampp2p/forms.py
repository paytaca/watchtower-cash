from django import forms
from .models import *

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