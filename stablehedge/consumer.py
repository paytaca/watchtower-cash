from main.rpc_consumer import RPCWebSocketConsumer, broadcast_rpc_event

from stablehedge import models

class Events:
    REDEMPTION_CONTRACT_TX_RESULT = "redemption_contract_tx_result"

    @classmethod
    def send_redemption_contract_tx_update(cls, obj:models.RedemptionContractTransaction):
        data = dict(
            id=obj.id,
            status=obj.status,
            txid=obj.txid,
            message=obj.result_message,
        )
        return broadcast_rpc_event(cls.REDEMPTION_CONTRACT_TX_RESULT, data=data)


class StablehedgeRpcConsumer(RPCWebSocketConsumer):
    Events = Events

    def rpc_get_redemption_tx_status(self, request, redemption_contract_tx_id):
        obj = models.RedemptionContractTransaction.objects.filter(id=redemption_contract_tx_id).first()
        if not obj:
            return dict(error="not_found")

        return dict(
            id=obj.id,
            status=obj.status,
            txid=obj.txid,
            message=obj.result_message,
        )
