# Generated migration to convert favorites from dict to list format

from django.db import migrations


def convert_favorites_to_list(apps, schema_editor):
    """
    Convert existing favorites data from dict format to list format.
    Handles:
    - {} (empty dict) → [] (empty list)
    - {"token_id": value} → [{"id": "token_id", "favorite": 1 if truthy else 0}]
    - Already a list → keep as is (but normalize structure)
    - None → []
    """
    AssetSetting = apps.get_model('main', 'AssetSetting')
    
    for asset_setting in AssetSetting.objects.all():
        favorites = asset_setting.favorites
        
        # If None, set to empty list
        if favorites is None:
            asset_setting.favorites = []
            asset_setting.save(update_fields=['favorites'])
            continue
        
        # If already a list, normalize it
        if isinstance(favorites, list):
            normalized = []
            for item in favorites:
                if isinstance(item, dict):
                    # Ensure structure is correct: {"id": str, "favorite": int}
                    item_id = item.get('id')
                    favorite_value = item.get('favorite', 0)
                    
                    # Normalize favorite to int (0 or 1)
                    if isinstance(favorite_value, str):
                        try:
                            favorite_value = int(favorite_value)
                        except (ValueError, TypeError):
                            favorite_value = 0
                    elif not isinstance(favorite_value, (int, float)):
                        favorite_value = 0
                    
                    # Ensure it's 0 or 1
                    favorite_value = 1 if favorite_value == 1 else 0
                    
                    # Only include items with valid id
                    if item_id:
                        normalized.append({
                            'id': str(item_id).strip(),
                            'favorite': int(favorite_value)
                        })
            asset_setting.favorites = normalized
            asset_setting.save(update_fields=['favorites'])
            continue
        
        # If dict, convert to list
        if isinstance(favorites, dict):
            if len(favorites) == 0:
                # Empty dict → empty list
                asset_setting.favorites = []
            else:
                # Convert dict to list format
                converted = []
                for key, value in favorites.items():
                    # Handle different value types
                    if isinstance(value, dict):
                        # If value is a dict, extract favorite from it
                        favorite_value = value.get('favorite', 0)
                        if isinstance(favorite_value, str):
                            try:
                                favorite_value = int(favorite_value)
                            except (ValueError, TypeError):
                                favorite_value = 0
                        elif not isinstance(favorite_value, (int, float)):
                            favorite_value = 0
                        else:
                            # Ensure it's 0 or 1
                            favorite_value = 1 if favorite_value == 1 else 0
                    else:
                        # If value is not a dict, treat truthy as favorite: 1
                        favorite_value = 1 if value else 0
                    
                    converted.append({
                        'id': str(key).strip(),
                        'favorite': int(favorite_value)
                    })
                asset_setting.favorites = converted
            asset_setting.save(update_fields=['favorites'])
            continue
        
        # Unknown type, set to empty list
        asset_setting.favorites = []
        asset_setting.save(update_fields=['favorites'])


def reverse_convert_favorites_to_dict(apps, schema_editor):
    """
    Reverse migration: convert list back to dict format (if needed for rollback).
    This converts [{"id": "token_id", "favorite": 1}, ...] back to {"token_id": 1}
    """
    AssetSetting = apps.get_model('main', 'AssetSetting')
    
    for asset_setting in AssetSetting.objects.all():
        favorites = asset_setting.favorites
        
        if isinstance(favorites, list):
            if len(favorites) == 0:
                asset_setting.favorites = {}
            else:
                converted = {}
                for item in favorites:
                    if isinstance(item, dict):
                        item_id = item.get('id')
                        favorite_value = item.get('favorite', 0)
                        if item_id:
                            # Convert to int if needed
                            if isinstance(favorite_value, str):
                                try:
                                    favorite_value = int(favorite_value)
                                except (ValueError, TypeError):
                                    favorite_value = 0
                            converted[str(item_id).strip()] = int(favorite_value) if favorite_value else 0
                asset_setting.favorites = converted
            asset_setting.save(update_fields=['favorites'])


class Migration(migrations.Migration):

    dependencies = [
        ('main', '0114_auto_20251116_1630'),
    ]

    operations = [
        migrations.RunPython(convert_favorites_to_list, reverse_convert_favorites_to_dict),
        migrations.AlterField(
            model_name='assetsetting',
            name='favorites',
            field=models.JSONField(default=list),
        ),
    ]
