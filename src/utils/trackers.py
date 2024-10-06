# Set up classes that allow tracking of items from one loop to the next
class Defective_Tracker:
    # Keeps track of which downloads were already caught as stalled previously
    def __init__(self, dict):
        self.dict = dict


class Download_Sizes_Tracker:
    # Keeps track of the file sizes of the downloads
    def __init__(self, dict):
        self.dict = dict


class Deleted_Downloads:
    # Keeps track of which downloads have already been deleted (to not double-delete)
    def __init__(self, dict):
        self.dict = dict
