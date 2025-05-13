from django.test import TestCase
from unittest.mock import patch
from django.urls import reverse
from .models import MultisigWallet, Signer
from rest_framework import status
import json

class MultisigWalletTests(TestCase):
    @patch('multisig.serializers.nonce_cache.get') 
    @patch('multisig.serializers.verify_signature')
    def test_create_multisig_wallet(self, mock_verify_signature, mock_nonce_get):
        # Mock success responses
        mock_nonce_get.return_value = True
        mock_verify_signature.return_value = True

        data = {
            "m": 2,
            "n": 3,
            "template": {
                "script_type": "p2sh",
                "network": "testnet"
            },
            "signers": [
                {
                    "xpub": "xpub6CUGRU...",
                    "derivation_path": "m/44'/0'/0'"
                },
                {
                    "xpub": "xpub6F5UZi...",
                    "derivation_path": "m/44'/0'/1'"
                },
                {
                    "xpub": "xpub6E2ZmL...",
                    "derivation_path": "m/44'/0'/2'"
                }
            ],
            "claimed_xpub": "xpub6CUGRU...",
            "signature": "deadbeef",
            "message": "nonce:abc123"
        }

        response = self.client.post("/wallets/", data=json.dumps(data), content_type='application/json')

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(MultisigWallet.objects.count(), 1)
        self.assertEqual(Signer.objects.count(), 3)
        self.assertIn("id", response.data)
