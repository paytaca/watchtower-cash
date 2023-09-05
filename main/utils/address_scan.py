import requests

def sort_address_sets(data):
    """
        Sorts an array of dictionaries by a key "address_index" in ascending order
    """
    address_sets = [*data]
    for i in range(len(address_sets)):
        min_index = i
        for j in range(i, len(address_sets)):
            if address_sets[min_index]["address_index"] > address_sets[j]["address_index"]:
                min_index = j
        address_sets[i], address_sets[min_index] = address_sets[min_index], address_sets[i]
    return address_sets


def get_bch_transactions(address, chipnet=False):
    network = "chipnet" if chipnet else "mainnet"
    url = f'http://localhost:3000/get-transactions/{address}/'
    params = dict(network=network)
    response = requests.get(url, params=params)
    return response.json()
