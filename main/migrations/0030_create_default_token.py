# Manually generated by developer 
from django.db import migrations

class Migration(migrations.Migration):
    dependencies = [
        ('main', '0029_auto_20200424_1109'),
    ]
    
    def create_default_token(apps, schema_editor):
        from main.models import Token
        Token.objects.get_or_create(
            name='spice',
            tokenid='4de69e374a8ed21cbddd47f2338cc0f479dc58daa2bbe11cd604ca488eca0ddf',
        )
        Token.objects.get_or_create(
            name='bch',
            tokenid='',
        )
        Token.objects.get_or_create(
            name='mist',
            tokenid='d6876f0fce603be43f15d34348bb1de1a8d688e1152596543da033a060cff798',
        )
        Token.objects.get_or_create(
            name='drop',
            tokenid='0f3f223902c44dc2bee6d3f77d565904d8501affba5ee0c56f7b32e8080ce14b',
        )
    
    operations = [
        migrations.RunPython(create_default_token)
    ]