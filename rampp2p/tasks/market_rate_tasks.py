from celery import shared_task
import subprocess
import json
import re

from rampp2p.utils.websocket import send_market_price
from rampp2p.models import MarketRate, FiatCurrency

import logging
logger = logging.getLogger(__name__)

@shared_task(queue='rampp2p__subprocess_execution')
def update_market_rates():
    '''
    Updates the market price records.
    '''
    logger.warning('Retrieving the market price of BCH')
    path = './rampp2p/js/src/'
    command = 'node {}rates.js'.format(path)
    return execute_subprocess.apply_async(
                (command,), 
                link=market_rates_beat_handler.s()
            )

@shared_task(queue='rampp2p__subprocess_execution')
def execute_subprocess(command):
    # execute subprocess
    logger.warning(f'executing: {command}')
    process = subprocess.Popen(command.split(), stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    stdout, stderr = process.communicate() 

    stderr = stderr.decode("utf-8")
    stdout = stdout.decode('utf-8')
    logger.warning(f'stdout: {stdout}, stderr: {stderr}')

    if stdout is not '':
        # Define the pattern for matching control characters
        control_char_pattern = re.compile('[\x00-\x1f\x7f-\x9f]')
        
        # Remove all control characters from the JSON string
        clean_stdout = control_char_pattern.sub('', stdout)

        stdout = json.loads(clean_stdout)
    
    response = {'result': stdout, 'error': stderr} 
    # logger.warning(f'response: {response}')

    return response

@shared_task(queue='rampp2p__subprocess_execution')
def market_rates_beat_handler(result):
    rates = result.get('result').get('rates')
    subbed_currencies = FiatCurrency.objects.values('symbol').all()
    logger.warn(f'subbed_currencies: {subbed_currencies}')

    for currency in subbed_currencies:
        symbol = currency.get('symbol')
        rate = rates.get(symbol)
        obj, created = MarketRate.objects.get_or_create(currency=symbol)
        obj.price = rate
        obj.save()
        
        if created:
            logger.warn(f'New market price | {obj.currency} : {obj.price}')
        else:
            logger.warn(f'Updated market price | {obj.currency} : {obj.price}')
        
        data =  { 'currency': obj.currency, 'price' : obj.price }
        send_market_price(data, currency)