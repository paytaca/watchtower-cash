from main import tasks
import json
from main.models import BlockHeight, Token, Transaction, SlpAddress, Subscription, BchAddress, SendTo

class SaveRecordTest(object):
	txid = None
	blockheight = None
	address = None
	spent_index = None
	amount = None
	source = None

	def test(self, *args, **kwargs):
		tasks.save_record(*args)
		transaction = Transaction.objects.get(txid=args[2], spentIndex=args[6])
		assert transaction
		if args[5] is not '':
			blockheight = BlockHeight.objects.get(number=args[5])
			assert blockheight
			self.blockheight = blockheight.number 
		if args[0] == 'bch':
			address = BchAddress.objects.get(address=args[1])
		else:
			address = SlpAddress.object.get(address=args[1])
		assert address
		self.txid = transaction.txid
		self.address = address.address
		self.spent_index = str(transaction.spentIndex)
		self.amount = str(transaction.amount)
		self.source = transaction.source
