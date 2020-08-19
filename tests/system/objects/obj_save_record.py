from main import tasks
import json
from main.models import BlockHeight, Token, Transaction, SlpAddress, Subscription, BchAddress, SendTo

class SaveRecordTest(object):
	txid = None
	address = None
	spent_index = None
	amount = None
	source = None

	def test(self, *args, **kwargs):
		# Execute the task that saves transaction.
		tasks.save_record(*args)

		# Counter Checking
		transaction = Transaction.objects.get(txid=args[2],address=args[1], spentIndex=args[6])
		assert transaction
		if args[5] is not None:
			blockheight = BlockHeight.objects.get(id=args[5])
			assert blockheight
		if args[0] == 'bch':
			address = BchAddress.objects.get(address=args[1])
		else:
			address = SlpAddress.object.get(address=args[1])
		assert address
		self.txid = transaction.txid
		self.address = address.address
		self.spent_index = transaction.spentIndex
		self.amount = transaction.amount
		self.source = transaction.source
	
	@staticmethod
	def build_payload(output):
		params = []
		if len(output) == 5:
			params = output.replace("'","").replace(")","").replace("(","").split(',')
			params = [x.strip() for x in params]
			if params[6] == 'None': params[6] = 0
			params[5] = eval(params[5])
			params[3] = eval(params[3])
		return params
