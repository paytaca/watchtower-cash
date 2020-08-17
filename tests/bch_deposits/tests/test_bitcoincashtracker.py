import mock
from pytest_mock import mocker
import pytest
from mock import patch

from main.utils import telegram
from main import tasks
from main.models import User, Deposit
from django.conf import settings
import json

@pytest.mark.django_db
def test_telegramBot_transaction(requests_mock, monkeypatch):
    telegramBot = TelegramBotTest(requests_mock, monkeypatch)
    #Default response in DM
    telegramBot.start(
        text="Hello buddy! I like you. This is my first chat",
        reply="What can I help you with?"
    )

    #Deposit
    telegramBot.deposit(
        text="deposit",
        reply="Depositing any tokens will credit your"
    )
    telegramBot.check_deposit()

    