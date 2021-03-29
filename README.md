## What is WatchTower.Cash? What does it intend to achieve?

- Instant and reliable infrastructure connecting you to the BitcoinCash Blockchain
- Redundant data sources (nodes and indexers) running on an elastic infrastructure
- The goal is to achieve and guarantee 99.99% uptime and reliability

## Webhook Subscription

To subscribe to webhook notifications, send a POST request to `https://watchtower.cash/api/webhook/subscribe` with the BCH or SLP address and the URL where the webhook calls will be sent. A sample CURL command show below:
```bash
curl -i -X POST 
    -H "Content-Type: application/json" 
    -d '{"address":"simpleledger:qr89dn8th7zj4n74vrqyce4vld522spunv3wkdqd5z", "web_url": "https://0f27bf32c670.ngrok.io"}' 
    https://watchtower.cash/api/webhook/subscribe
```

A POST request notification is sent to the URL if a new transcation is detected. A sample notification is shown below:
```python
{
    'source': 'WatchTower',
    'address': 'simpleledger:qr89dn8th7zj4n74vrqyce4vld522spunv3wkdqd5z',
    'txid': '2cb0b57c9a8cad95d08f9b408b77802961d473abf71f0ec30669f9c2272f3d82',
    'token': '7f8889682d57369ed0e32336f8b7e0ffec625a35cca183f4e81fde4e71a538a1',
    'index': 1,
    'amount': 321.0
}
```
