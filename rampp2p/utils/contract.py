from rampp2p.tasks.task_contract import generate_contract, contract_handler, contract_error_handler

def create_contract(**kwargs):
    '''
    Executes a subprocess task to generate the contract address
    '''
    return generate_contract.apply_async(
        kwargs={
            'arbiter_pubkey': kwargs.get('arbiter_pubkey'),
            'buyer_pubkey': kwargs.get('buyer_pubkey'),
            'seller_pubkey': kwargs.get('seller_pubkey'),
            'timestamp': kwargs.get('timestamp'),
            'service_fee': kwargs.get('service_fee'),
            'arbitration_fee': kwargs.get('arbitration_fee'),
        },
        link=contract_handler.s(
            order_id=kwargs.get('order_id')
        ),
        link_error=contract_error_handler.s(order_id=kwargs.get('order_id')),
    )
