from django.conf import settings
import subprocess

class Contract():
    def __init__(self, arbiterPk, buyerPk, sellerPk):
        self.arbiterPk = arbiterPk
        self.buyerPk = buyerPk
        self.sellerPk = sellerPk
        self.servicerPk = settings.SERVICER_PK
        self.servicerAddr = settings.SERVICER_ADDR
        self.tradingFee = int(settings.TRADING_FEE)
        self.arbitrationFee = int(settings.ARBITRATION_FEE)
        self.address = self.generate_contract(
            self.arbiterPk, 
            self.buyerPk, 
            self.sellerPk
        )
    
    def execute(self, command):
        process = subprocess.Popen(command.split(), stdout=subprocess.PIPE)
        # capture the output and errors
        output, error = process.communicate()  
        if error is not None:
           raise ContractError(error.decode('utf-8'))
        return output.decode('utf-8')
    
    def generate_contract(self, arbiterPk, buyerPk, sellerPk):
        path = './rampp2p/escrow/src/'
        command = 'node {}escrow.js contract {} {} {}'.format(
           path,
           arbiterPk, 
           sellerPk, 
           buyerPk
        )
        return self.execute(command)

    def release(self, action, callerPubkey, callerSig, recipientAddr, arbiterAddr, amount):        
        path = './rampp2p/escrow/src/'
        command = 'node {}escrow.js {} {} {} {} {} {} {} {}'.format(
            path,
            action,
            self.arbiterPk, 
            self.sellerPk, 
            self.buyerPk,
            callerSig,
            recipientAddr,
            arbiterAddr,
            amount,
        )
        return self.execute(command)

    def refund(self, arbiterPk, arbiterSig, recipientAddr, arbiterAddr, amount):
        path = './rampp2p/escrow/src/'
        command = 'node {}escrow.js refund {} {} {} {} {} {} {} {} {} {}'.format(
            path,
            self.arbiterPk, 
            self.sellerPk, 
            self.buyerPk,
            arbiterSig, 
            recipientAddr,
            arbiterAddr, 
            amount
        )
        return self.execute(command)

class ContractError(Exception):
    def __init__(self, message):
        self.message = message
    
    def __str__(self):
        return self.message