# Manually generated by developer 
from django.db import migrations

class Migration(migrations.Migration):
    dependencies = [
        ('main', '0029_auto_20200424_1109'),
    ]
    
    def create_default_token(apps, schema_editor):
        pass
    
    operations = [
        migrations.RunPython(create_default_token)
    ]