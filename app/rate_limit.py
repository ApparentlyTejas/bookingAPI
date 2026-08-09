"""
Shared Limiter instance. Lives in its own module (not app/main.py) so
routers can import it without a circular import — main.py imports the
routers, so a router can't import the limiter back out of main.py.
"""

from slowapi import Limiter
from slowapi.util import get_remote_address

limiter = Limiter(key_func=get_remote_address)
