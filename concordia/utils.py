# TODO: include standard copyright header

import sys
import os


def import_Config(path=None):
    PROJECT_DIR = os.path.dirname(os.path.abspath(__file__))
    BASE_DIR = os.path.dirname(PROJECT_DIR)

    sys.path.append(BASE_DIR)

    sys.path.append(os.path.join(BASE_DIR, "config"))
    from config import Config
