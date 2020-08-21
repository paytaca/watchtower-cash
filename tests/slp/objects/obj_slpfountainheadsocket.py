from django.conf import settings
import json, requests
from main import tasks
import requests_mock
import pytest
import requests


class SLPFountainheadSocketTest(object):	

    def __init__(self, requests_mock, capsys):
        self.url = 'https://slpsocket.fountainhead.cash/s/ewogICJ2IjogMywKICAicSI6IHsKICAgICJmaW5kIjogewogICAgfQogIH0KfQ=='
        self.expectation = ''
        self.output = ''
        self.requests_mock = requests_mock
        self.capsys = capsys
        
    
    def test(self):
        self.requests_mock.get(self.url, text=self.expectation)        
        captured = self.capsys.readouterr()
        assert captured.out == self.output
        