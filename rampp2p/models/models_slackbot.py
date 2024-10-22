from django.db import models
from django.conf import settings
from jsonfield import JSONField
from slack import WebClient

# Create your models here.
class SlackMessageLog(models.Model):
    class Topic(models.TextChoices):
        AD_SUMMARY = "ad_summary"                   
        AD_UPDATE = "ad_update"                     
        ORDER_SUMMARY = "order_summary"             
        ORDER_STATUS_UPDATE = "order_status_update" 
        APPEAL_SUMMARY = "appeal_summary"           
        APPEAL_UPDATE = "appeal_update"             

    topic = models.CharField(max_length=50, choices=Topic.choices)
    object_id = models.BigIntegerField()
    metadata = JSONField(
        null=True, blank=True,
        help_text="Arbitrary data to add context to the message",
    )

    channel = models.CharField(max_length=50)
    ts = models.DecimalField(max_digits=18, decimal_places=6) # also serves as messageid
    thread_ts = models.DecimalField(
        max_digits=18, decimal_places=6,
        null=True, blank=True,
    ) # if the message is a reply

    permalink = models.URLField(null=True, blank=True)
    deleted_at = models.DateTimeField(null=True, blank=True)

    def get_permalink(self, force=False,):
        if self.permalink and not force:
            return self.permalink

        client = WebClient(token=settings.SLACK_API_TOKEN)
        response = client.chat_getPermalink(channel=self.channel, message_ts=str(self.ts))

        if not response.get("ok"): return

        self.permalink = response["permalink"]
        self.save()
        return self.permalink
