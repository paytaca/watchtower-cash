# Manually generated by developer

from django.db import migrations

class Migration(migrations.Migration):

    dependencies = [
        ('main', '0029_auto_20200424_1109'),
    ]

    def create_default_token(apps, schema_editor):
        from main.models import Token
        Token.objects.get_or_create(
            name='spice',
            tokenid='4de69e374a8ed21cbddd47f2338cc0f479dc58daa2bbe11cd604ca488eca0ddf',
        )

    operations = [
        migrations.RunPython(create_default_token)
    ]