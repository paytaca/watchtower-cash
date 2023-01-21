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
- Passing `gcm_device` or `apns_device` object will create a `push_notifications.GCMDevice` or `push_notifications.APNSDevice` instance, respectively. The API will search for an existing record on `push_notifications.GCMDevice` or `push_notifications.APNSDevice` with the same `registration_id` first before creating a new instance.

- `wallet_hashes` will create a set of `notifications.DeviceWallet` that will be linked to the created `push_notifications.GCMDevice` or `push_notifications.APNSDevice`. This will sync with the existing records (if there are any)
  - existing records that are not in `wallet_hashes` will be removed
  - non-existing records that are in `wallet_hashes` will be added


## Sending push notifications to specific wallet
There are a set of util functions that can be used to send push notifications to a wallet in `notifications.utils.send`:
  - `get_wallet_hashes_devices(wallet_hash_list)`: This returns a 2-tuple queryset of (`GCMDevice`, `APNSDevice`) that are linked to any wallet_hash in the list provided
  - `send_push_notification_to_wallet_hashes(wallet_hash_list, message, **kwargs)`: Sends a push notification to `GCMDevices` & `APNSDevices` given a list of wallet hashes
    - returns a 2 tuple of responses from sending to `GCMDevices` & `APNSDevices`, respectively
    - sending to each device types will fail silently causing one or both of the results can be an Exception. This is to not stop sending to the other device type if one fails

Using utils functions:
```
from notifications.utils.send import send_get_wallet_hashes_devices

wallet_hash = "wallet-hash-here"

hidden_data = { "foo": "bar" }
title = "Notification title"
message = "Test notification"

response = send_get_wallet_hashes_devices([wallet_hash], message, title=title, extra=hidden_data)
(gcm_send_response, apns_send_response) = response
```

You can achieve the same results without the utils function with the following example:
```
from push_notifications.models import GCMDevice, APNSDevice

wallet_hash = "wallet-hash-here"
gcm_devices = GCMDevice.objects.filter(wallet_devices__wallet_hash=wallet_hash)
apns_devices = APNSDevice.objects.filter(wallet_devices__wallet_hash=wallet_hash)

hidden_data = { "foo": "bar" }
title = "Notification title"
message = "Test notification"

gcm_send_response = gcm_devices.send_message(message, title=title, extra=hidden_data)
apns_send_response = apns_devices.send_message(message, title=title, extra=hidden_data)
```
