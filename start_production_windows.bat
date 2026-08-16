@echo off
set FLASK_ENV=production
set FLASK_DEBUG=0
waitress-serve --listen=0.0.0.0:8000 wsgi:app
