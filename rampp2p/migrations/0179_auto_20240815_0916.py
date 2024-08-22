# Generated by Django 3.0.14 on 2024-08-15 09:16

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('rampp2p', '0178_auto_20240731_0847'),
    ]

    operations = [
        migrations.CreateModel(
            name='ImageUpload',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('url', models.URLField(blank=True, null=True)),
                ('url_path', models.CharField(blank=True, max_length=256, null=True)),
                ('file_hash', models.CharField(blank=True, max_length=70, null=True, unique=True)),
                ('size', models.IntegerField(blank=True, null=True)),
            ],
        ),
        migrations.CreateModel(
            name='OrderPaymentAttachment',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('image', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to='rampp2p.ImageUpload')),
            ],
        ),
        migrations.RenameModel(
            old_name='OrderPaymentMethod',
            new_name='OrderPayment',
        ),
        migrations.DeleteModel(
            name='Receipt',
        ),
        migrations.AddField(
            model_name='orderpaymentattachment',
            name='payment',
            field=models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to='rampp2p.OrderPayment'),
        ),
    ]
