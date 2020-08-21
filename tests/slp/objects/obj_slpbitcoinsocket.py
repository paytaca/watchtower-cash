from django.conf import settings
import json, requests
from main import tasks
import requests_mock
import pytest
import requests


class SlpBitcoinSocketTest(object):	

    def __init__(self, requests_mock, capsys):
        self.url = 'https://slpsocket.bitcoin.com/s/ewogICJ2IjogMywKICAicSI6IHsKICAgICJmaW5kIjoge30KICB9Cn0='
        self.output = '' # Get back into this soon. (Reamon Sumapig)
        self.expectation = ''
        self.requests_mock = requests_mock
        self.capsys = capsys
    
    def test(self):
        self.requests_mock.get(self.url, text=self.expectation)
        # tasks.bitcoincash_tracker()
        captured = self.capsys.readouterr()
        assert captured.out == self.output
        