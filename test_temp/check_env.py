#!/usr/bin/env python3
"""检查 startup_checks 行为"""
import os
from dotenv import load_dotenv

print(f'BEFORE load_dotenv: FLASK_DEBUG={os.environ.get("FLASK_DEBUG", "NOT_SET")}')
load_dotenv()
print(f'AFTER load_dotenv: FLASK_DEBUG={os.environ.get("FLASK_DEBUG", "NOT_SET")}')

# Simulate dev.py: setdefault FIRST
os.environ.pop('FLASK_DEBUG', None)
os.environ.setdefault('FLASK_DEBUG', 'True')
print(f'After setdefault: FLASK_DEBUG={os.environ.get("FLASK_DEBUG")}')

# Then load_dotenv
load_dotenv()
print(f'After load_dotenv 2nd: FLASK_DEBUG={os.environ.get("FLASK_DEBUG")}')

# Check
flask_debug = os.environ.get('FLASK_DEBUG', 'false').lower()
is_debug = flask_debug == 'true'
print(f'is_debug: {is_debug}')
