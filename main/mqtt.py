import paho.mqtt.client as mqtt

client = mqtt.Client(transport='websockets')
client.tls_set()
client.connect('mqtt.watchtower.cash', 443, 10)
