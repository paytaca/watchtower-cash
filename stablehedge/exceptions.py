
class StablehedgeException(Exception):
    def __init__(self, *args, code=None, **kwargs):
        self.code = code
        super().__init__(*args, **kwargs)
