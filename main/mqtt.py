import paho.mqtt.client as mqtt

client = mqtt.Client()
client.connect("docker-host", 1883, 10)
