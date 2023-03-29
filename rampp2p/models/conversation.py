from django.db import models

class Conversation(models.Model):
  members = models.ManyToManyField('Peer')
  created_at = models.DateTimeField(auto_now_add=True, editable=False)

  # TODO: should not be deletable

class Message(models.Model):
  from_peer = models.ForeignKey('Peer', on_delete=models.PROTECT, editable=False)
  chat_room = models.ForeignKey('ChatRoom', on_delete=models.PROTECT, editable=False)
  message = models.CharField(max_length=4000, editable=False)
  created_at = models.DateTimeField(auto_now_add=True, editable=False)