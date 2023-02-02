from django.core.management.base import BaseCommand

import json
from anyhedge.tests.data.factory import generate_random_contract

class Command(BaseCommand):
    help = "Creates/updates test data files/fixtures"

    def handle(self, *args, **options):
        data = generate_random_contract(save_to_file="./anyhedge/tests/data/anyhedge-test-data.json")
        print(json.dumps(data, indent=4))
