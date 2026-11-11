"""ASGI entry point of the UniBridge profile: uvicorn p14_search.unibridge_main:app --port 8001"""

from p14_search.api.app import create_app
from p14_search.unibridge_profile import unibridge_settings

app = create_app(unibridge_settings())
