# Ideally put all files/code pulled from outside the app(anyhedge) in here
from main.utils.queries.bchd import BCHDQuery

def get_bchd_instance():
    return BCHDQuery()
