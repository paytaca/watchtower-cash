from django import forms
from .models import *

class FiatCurrencyForm(forms.ModelForm):
    cashin_presets = forms.CharField(widget=forms.Textarea, required=False)

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