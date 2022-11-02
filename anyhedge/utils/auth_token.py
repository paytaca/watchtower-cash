from ..js.runner import AnyhedgeFunctions

def get_settlement_service_auth_token(scheme, domain, port, raise_exception=False):
    try:
        return AnyhedgeFunctions.getSettlementServiceAuthToken({
            "scheme": scheme,
            "domain": domain,
            "port": port,
        })
    except Exception as exception:
        if raise_exception:
            raise exception
