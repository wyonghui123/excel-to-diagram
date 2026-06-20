print("hello from python")
import sys
print(f"python: {sys.version}")
import os
print(f"cwd: {os.getcwd()}")
print(f"script dir: {os.path.dirname(os.path.abspath(__file__))}")