from django.db import migrations


NOSTR_GROUP_ID_LEN = 64


def has_uppercase(value):
    return any(c.isupper() for c in value)


def lowercase_group_ids(apps, schema_editor):
    NostrRoom = apps.get_model('nostr', 'NostrRoom')
    qs = NostrRoom.objects.exclude(nostr_group_id__isnull=True).only('id', 'nostr_group_id')
    for room in qs.iterator(chunk_size=200):
        gid = room.nostr_group_id
        if not gid:
            continue
        if not has_uppercase(gid):
            continue
        # The model validations reject anything other than a 64-char lowercase
        # hex string; rows that would now fail validation are skipped so the
        # migration is idempotent for clean rows and a no-op for corrupt ones.
        if len(gid) != NOSTR_GROUP_ID_LEN:
            continue
        try:
            int(gid, 16)
        except ValueError:
            continue
        NostrRoom.objects.filter(pk=room.pk).update(nostr_group_id=gid.lower())


def noop_reverse(apps, schema_editor):
    # Lower-casing existing values is safe; we don't restore the original
    # casing because we didn't snapshot it.
    pass


class Migration(migrations.Migration):

    dependencies = [
        ('nostr', '0010_nostrroom_nostr_group_id'),
    ]

    operations = [
        migrations.RunPython(lowercase_group_ids, noop_reverse),
    ]
