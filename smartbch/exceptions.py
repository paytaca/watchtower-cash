from rest_framework.exceptions import APIException

class InvalidQueryParameterException(APIException):
    status_code = 400
    default_detail = "Invalid query parameter value"
    default_code = "invalid_query_parameter"
