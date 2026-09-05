"""WSGI entry point."""

from flask import Flask

from backend.app import create_app

app: Flask = create_app()
