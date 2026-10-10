"""One process-default Web composition; independent apps use create_application."""
from .application import create_application

default_application = create_application()
