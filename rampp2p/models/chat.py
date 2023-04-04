from django.db import models

from .peer import Peer
from .chat import Chat, Message

class Chat(models.Model):
  members = models.ManyToManyField(Peer)
  created_at = models.DateTimeField(auto_now_add=True, editable=False)

  # TODO: should not be deletable

class Message(models.Model):
  from_peer = models.ForeignKey(Peer, on_delete=models.CASCADE, editable=False)
  chat = models.ForeignKey(Chat, on_delete=models.CASCADE, related_name="messages", editable=False)
  message = models.CharField(max_length=4000, editable=False)
  sent_at = models.DateTimeField(auto_now_add=True, editable=False)

class Image(models.Model):
  message = models.ForeignKey(Message, on_delete=models.CASCADE, related_name="images", editable=False)
  url = models.CharField(max_length=100, editable=False)
  uploaded_at = models.DateTimeField(auto_now_add=True)

# def upload_directory_path(instance):
#   # file will be uploaded to MEDIA_ROOT/chat_uploads/<peer_id>/<year>/<month>/<day>/<chat_id>/<message_id>/
#   return 'chat_uploads/peer_{0}/%Y/%m/%d/{1}/{2}/'.format(instance.message.from_peer, instance.message.chat.id, instance.message.id)