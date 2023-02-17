import re
from urllib.parse import urlparse

# Possible ipfs gateways to use is not working
# taken from https://ipfs.github.io/public-gateway-checker/
ipfs_gateways = [
    "ipfs-gateway.cloud",
    "gateway.pinata.cloud",
    "cloudflare-ipfs.com",
    "nftstorage.link",
    "ipfs.filebase.io",
]

def get_ipfs_cid_from_url(url):
    ipfs_path_regex = "^/?ipfs/([a-zA-Z0-9]+)/?$"
    try:
        parsed_url = urlparse(url)
        if parsed_url.scheme == 'ipfs' and parsed_url.netloc:
            return parsed_url.netloc
        match = re.match(ipfs_path_regex, parsed_url.path)
        if match:
            return match.group(1)
    except (AttributeError, ValueError):
        pass
    return None
