# Notifications
This app manages subscribing of devices for push notifications to android & ios devices. This app uses a third party package for push notifications in django: [django-push-notifications](https://github.com/jazzband/django-push-notifications/)

## Models
### `push_notifications.GCMDevice` & `push_notifications.APNSDevice`
models from `django-push-notifications` library for keeping records of `registration_id`s for android(GCMDevice) & ios(APNSDevice)
`GCMDevice` & `APNSDevice` also has built in function `.send_messsage()` for sending push notifications that works both on per instance & querysets.

### `notifications.DeviceWallet`
This model acts as the junction table between `main.Wallet` & `push_notifications.GCMDevice`, `push_notifications.APNSDevice` to allow sending push notifications to specific wallets.
```
class DeviceWallet(models.Model):
    gcm_device = models.ForeignKey(push_notifications.GCMDevice, null=True)
    apns_device = models.ForeignKey(push_notifications.APNSDevice, null=True)
    wallet_hash = models.CharField(...)
    last_active = models.DateTimeField()
```

## API
### Device Registration - `'/push-notifications/subscribe/'`
Creates a `push_notifications.GCMDevice` or `push_notifications.APNSDevice` and a set of `notifications.DeviceWallet` records

The API expects the following payload:
```
{
    "gcm_device" | "apns_device" : {
        "registration_id": string,
        "device_id": uuid | integer, // ios | android
        "name": string,
        "application_id": string,
    },
    "wallet_hashes": string[],
}
```
- Passing `gcm_device` or `apns_device` object will create a `push_notifications.GCMDevice` or `push_notifications.APNSDevice` instance, respectively. The API will search for an existing record on `push_notifications.GCMDevice` or `push_notifications.APNSDevice` with the same `application_id` first before creating a new instance.

- `wallet_hashes` will create a set of `notifications.DeviceWallet` that will be linked to the created `push_notifications.GCMDevice` or `push_notifications.APNSDevice`. This will sync with the existing records (if there are any)
  - existing records that are not in `wallet_hashes` will be removed
  - non-existing records that are in `wallet_hashes` will be added


## Sending push notifications to specific wallet
```
from push_notifications.models import GCMDevice, APNSDevice

wallet_hash = "wallet-hash-here"
gcm_devices = GCMDevice.objects.filter(wallet_devices__wallet_hash=wallet_hash)
apns_devices = APNSDevice.objects.filter(wallet_devices__wallet_hash=wallet_hash)

hidden_data = { "foo": "bar" }
title = "Notification title"
message = "Test notification"

gcm_devices.send_message(message, title=title, extra=hidden_data)
apns_devices.send_message(message, title=title, extra=hidden_data)
```
