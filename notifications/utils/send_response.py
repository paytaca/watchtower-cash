from firebase_admin import messaging

def parse_gcm_response(gcm_response):
    if isinstance(gcm_response, messaging.BatchResponse):
        return [parse_gcm_response(resp) for resp in gcm_response.responses]

    if isinstance(gcm_response, messaging.SendResponse):
        return {
            "success": gcm_response.success,
            "msg_id": gcm_response.message_id,
            "exception":gcm_response.exception,
        }
    return gcm_response

def has_successful_response(gcm_send_response, apns_send_response):
    if isinstance(gcm_send_response, Exception) and isinstance(apns_send_response, Exception):
        return False

    if isinstance(gcm_send_response, list):
        for gcm_response in gcm_send_response:
            if isinstance(gcm_response, messaging.BatchResponse) and gcm_response.success_count > 0:
                return True
            elif isinstance(gcm_response, messaging.SendResponse) and gcm_response.success:
                return True
            elif isinstance(gcm_response, dict) and gcm_response.get("success"):
                return True

    if isinstance(apns_send_response, list):
        for apns_response in apns_send_response:
            if not isinstance(apns_response, dict):
                continue
            if any([result == 'Success' for result in apns_response.values()]):
                return True

    return False

