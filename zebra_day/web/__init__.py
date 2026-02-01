"""
zebra_day web application module.

FastAPI-based web interface for managing Zebra printers and label templates.
"""
from zebra_day.web.app import create_app

__all__ = ["create_app"]

