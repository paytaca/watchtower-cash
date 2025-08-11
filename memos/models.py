from django.db import models

# Create your models here.
class Memo(models.Model):        
    wallet_hash = models.CharField(max_length=75, unique=True, db_index=True)
    created_at = models.DateTimeField(auto_now_add=True, editable=False)
    instructions = models.TextField(blank=True, null=True)