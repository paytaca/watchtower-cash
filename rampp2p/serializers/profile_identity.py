from rest_framework import serializers


class ImmutableProfileIdentityMixin:
    """General profile updates cannot rotate a registered wallet identity."""

    identity_fields = ('public_key', 'address', 'address_path', 'wallet_hash')

    def validate(self, attrs):
        attrs = super().validate(attrs)
        if self.instance is not None:
            errors = {
                field: 'Registered identity cannot be changed through profile updates.'
                for field in self.identity_fields
                if field in attrs and attrs[field] != getattr(self.instance, field)
            }
            if errors:
                raise serializers.ValidationError(errors)
        return attrs

    def update(self, instance, validated_data):
        # Save only metadata fields; a stale authenticated instance must not
        # overwrite an identity changed by a separate administrative operation.
        changed_fields = []
        for field, value in validated_data.items():
            if field not in self.identity_fields:
                setattr(instance, field, value)
                changed_fields.append(field)
        if changed_fields:
            instance.save(update_fields=changed_fields + ['modified_at'])
        instance.refresh_from_db(fields=self.identity_fields)
        return instance
