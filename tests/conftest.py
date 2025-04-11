import os
import sys

# Add the repository root directory (which contains the "src" folder) to sys.path.
root_directory = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
if root_directory not in sys.path:
    sys.path.insert(0, root_directory)
