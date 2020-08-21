from django.conf import settings
import json, requests
from main import tasks
from main.models import BlockHeight
import requests_mock

import pytest
import requests


class SlpstreamFountainheadSocket(object):	

    def __init__(self, requests_mock, capsys):
        self.requests_mock = requests_mock
        self.capsys = capsys
        self.url = f"https://slpstream.fountainhead.cash/s/ewogICJ2IjogMywKICAicSI6IHsKICAgICJmaW5kIjoge30KICB9Cn0="
        self.expectation = ""
        self.output = ""

    
    def test(self):
        self.requests_mock.get(self.url, text=self.expectation)
        captured = self.capsys.readouterr()
        assert captured.out == self.output
        