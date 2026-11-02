"""Start the app: python -m gradepath [data.db] [--port 8022]"""
import sys

from .fieldkit import main_cli
from .web import create_app

sys.exit(main_cli(create_app, "gradepath.db", 8022, sys.argv))
