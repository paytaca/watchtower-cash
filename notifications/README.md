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

`last_active` records when a subscribe call last refreshed the link. It is
bookkeeping only — it no longer drives send selection or ordering.

A device may link to a wallet hash at most once (`unique_wallet_hash_per_gcm_device` /
`unique_wallet_hash_per_apns_device`). Push sending fans out per linked device, so a
duplicate row here means a duplicate notification for the same transaction.

> The old `multi_wallet_index` column is gone. It recorded the app's vault *position*,
> which shifts whenever the user reorders or removes a vault, so it was never a stable
> identity — and grouping sends by it produced one identical notification per index the
> wallet had ever occupied.

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
  - non-existing records that are in `wallet_hashes` will be added
  - **subscribing is additive**: existing records that are *not* in `wallet_hashes` are left alone

Subscribing is additive because a client only knows the wallet the user currently has open. Installed apps re-subscribe on every launch and wallet switch with just the active wallet's hashes, so treating the list as the device's complete set would unlink every other vault on the device and silently stop its notifications.

A client that does send its whole set can opt in to replacement semantics:

```
{
    ...,
    "wallet_hashes": string[],
    "prune_unlisted": true,   // optional, default false
}
```

With `prune_unlisted: true`, `DeviceWallet` rows for this device whose `wallet_hash` is not in the list are deleted. To stop receiving notifications for a wallet, use `'/push-notifications/unsubscribe/'`.


## Sending push notifications to specific wallet
There are a set of util functions that can be used to send push notifications to a wallet in `notifications.utils.send`:
  - `get_wallet_hashes_devices(wallet_hash_list)`: This returns a 2-tuple queryset of (`GCMDevice`, `APNSDevice`) that are linked to any wallet_hash in the list provided
  - `send_push_notification_to_wallet_hashes(wallet_hash_list, message, **kwargs)`: Sends a push notification to `GCMDevices` & `APNSDevices` given a list of wallet hashes
    - returns a 2 tuple of responses from sending to `GCMDevices` & `APNSDevices`, respectively
    - sending to each device types will fail silently causing one or both of the results can be an Exception. This is to not stop sending to the other device type if one fails
  - `NotificationTypes`: a class containing the different types of push notifications.
    - This is helpful for devices to perform the appropriate the routing & actions when displaying the notification in app

> NOTE: It is highly encouraged for every push notification sent to include a `type` key in the `extra` payload. Preferrably something from `notifications.utils.send.NotificationTypes`.

Using utils functions:
```
from notifications.utils.send import send_push_notification_to_wallet_hashes

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
