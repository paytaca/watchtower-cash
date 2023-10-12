from rest_framework.exceptions import APIException

class InvalidSignature(APIException):
    status_code = 403
    default_detail = 'Invalid Signature'
    default_code = 'invalid_signature'

    def __init__(self, detail=None, error=None):
        if error is not None:
            detail = f'{self.default_detail} Error: {error}'
        super().__init__(detail=detail, code=self.default_code)