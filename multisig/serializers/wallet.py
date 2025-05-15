import re
import json
import hashlib
import logging
from django.db import transaction
from rest_framework import serializers
from ..models.wallet import MultisigWallet, Signer
from ..utils import get_multisig_wallet_locking_script
LOGGER = logging.getLogger(__name__)


class SignerSerializer(serializers.ModelSerializer):
    class Meta:
        model = Signer
        fields = ['entity_key', 'xpub']

class MultisigWalletSerializer(serializers.ModelSerializer):
    signers = SignerSerializer(many=True, read_only=True)
    # template_name = serializers.CharField(source='template.name', required=False)
    lockingData = serializers.JSONField(source='locking_data')
    template = serializers.JSONField()

    class Meta:
        model = MultisigWallet
        fields = ['id', 'template', 'lockingData', 'signers', 'created_at', 'locking_bytecode']
        read_only_fields = ['signers', 'created_at']
    
    # def to_representation(self, instance):
        
    #     rep = super().to_representation(instance)

    #     def extract_sort_key(key):
    #         match = re.search(r'_(\d+)$', key)
    #         return int(match.group(1)) if match else float('inf')

    #     hd_public_keys = dict(
    #         sorted(
    #             (
    #                 (signer.key, signer.value)
    #                 for signer in instance.signer_hd_public_keys.all()
    #             ),
    #             key=lambda item: (extract_sort_key(item[0]), item[0])  # fallback to alpha sort if needed
    #         )
    #     )

    #     rep['lockingData'] = {
    #         'hdKeys': {
    #             'addressIndex': instance.locking_data.get('hdKeys', {}).get('addressIndex', 0),
    #             'hdPublicKeys': hd_public_keys
    #         }
    #     }

    #     LOGGER.info(instance.template.json)

    #     return {
    #         'id': instance.id,
    #         'template': instance.template.json,
    #         'lockingData': rep['lockingData']
    #     }
    
    # @staticmethod
    # def get_or_create_template(template_json):
    #     canonical = json.dumps(template_json, sort_keys=True)
    #     template_hash = hashlib.sha256(canonical.encode()).hexdigest()
    #     template, created = MultisigTemplate.objects.get_or_create(
    #         hash=template_hash,
    #         defaults=template_json
    #     )
    #     return template
    
    def create(self, validated_data):
        # locking_data = validated_data.pop('locking_data', {})
        locking_data = validated_data.get('locking_data', {})
        template = validated_data.get('template', {})
        with transaction.atomic():
            # template = MultisigWalletSerializer.get_or_create_template(template_json)
            locking_bytecode = get_multisig_wallet_locking_script(template, locking_data)
            wallet, created = MultisigWallet.objects.get_or_create(
                locking_bytecode=locking_bytecode,
                defaults= {
                    'template': template,
                    'locking_data':locking_data,
                    'locking_bytecode':locking_bytecode    
                }
                # template=template,
                # locking_data=locking_data,
                # locking_bytecode=locking_bytecode
            )
            
            if created:
                hd_public_keys = locking_data.get('hdKeys', {}).get('hdPublicKeys', {})
                for key, value in hd_public_keys.items():
                    Signer.objects.create(
                        wallet=wallet,
                        entity_key=key,
                        xpub=value
                    )

        return wallet


    # def update(self, instance, validated_data):
    #     template_updates = validated_data.pop('template', {})
        
    #     # Update template.name only if present
    #     if 'name' in template_updates:
    #         instance.template['name'] = template_updates['name']

    #     # Update any other top-level fields if necessary
    #     for attr, value in validated_data.items():
    #         setattr(instance, attr, value)

    #     instance.save()
    #     return instance


    # OP_HASH160 <20-byte script hash> OP_EQUAL
    # => 'a9' + '14' + <hash160> + '87'
#     >>> from bitcash.format import address_to_public_key_hash
# >>> address_to_public_key_hash('bitcoincash:pplldqjpjaj0058xma6csnpgxd9ew2vxgvwghanjr2')
# b'\x7f\xf6\x82A\x97d\xf7\xd0\xe6\xdfu\x88L(3K\x97)\x86C'
# >>> a = address_to_public_key_hash('bitcoincash:pplldqjpjaj0058xma6csnpgxd9ew2vxgvwghanjr2')
# >>> str(a)
# "b'\\x7f\\xf6\\x82A\\x97d\\xf7\\xd0\\xe6\\xdfu\\x88L(3K\\x97)\\x86C'"
# >>> a.to_string()
# Traceback (most recent call last):
#   File "<stdin>", line 1, in <module>
# AttributeError: 'bytes' object has no attribute 'to_string'
# >>> a.hex()
# '7ff682419764f7d0e6df75884c28334b97298643'
# >>> 