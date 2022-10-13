from django.db import models

class PosDevice(models.Model):
    posid = models.IntegerField()
    wallet_hash = models.CharField(max_length=70)

    name = models.CharField(max_length=100, null=True, blank=True)

    class Meta:
        unique_together = (
            ("posid", "wallet_hash"),
        )

    @classmethod
    def find_new_posid(cls, wallet_hash):
        queryset = cls.objects.filter(wallet_hash=wallet_hash)
        last_posid = queryset.aggregate(max=models.Max("posid"))["max"]
        if last_posid is not None and last_posid+1 < 10 ** 4:
            return last_posid + 1

        posids = queryset.values_list("posid").distinct()
        for i in range(10**4):
            if i not in posids:
                return i

        return None
