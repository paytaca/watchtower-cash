from django.shortcuts import render
from django.views import View
import hashlib
from paytacagifts.models import Gift

def generate_gift_code_hash(gift_code):
    return hashlib.sha256(gift_code.encode()).hexdigest()


class GiftClaimView(View):

    def get(self, request):
        gift_code = request.GET.get('code', '')
        gift_code_hash = generate_gift_code_hash(gift_code)
        gift = Gift.objects.filter(gift_code_hash=gift_code_hash).first()
        exists = False
        amount = None
        claimed = False
        if gift:
            exists = True
            amount = float(gift.amount)
            if gift.date_claimed:
                claimed = True

        context = {
            "code": gift_code,
            "exists": exists,
            "amount": amount,
            "claimed": claimed,
            "title": f"This link delivers {amount} BCH gift!",
            "description": "This link delivers a Bitcoin Cash (BCH) gift you can claim using the Paytaca wallet app."
        }
        return render(request, "gift.html", context=context)