import os
import re

# Files to fix - these use os.path.dirname(os.path.dirname(os.path.dirname(__file__))) which goes up 3 levels
# Should use os.path.dirname(os.path.dirname(__file__)) which goes up 2 levels

files_to_fix = []

# Check test_date_format_api.py
test_file = 'd:/filework/excel-to-diagram/meta/tests/test_date_format_api.py'
if os.path.exists(test_file):
    with open(test_file, 'r', encoding='utf-8') as f:
        content = f.read()
    
    # Fix the pattern: os.path.dirname(os.path.dirname(os.path.dirname(__file__)))
    # Should be: os.path.dirname(os.path.dirname(__file__))
    fixed = re.sub(
        r"os\.path\.dirname\(os\.path\.dirname\(os\.path\.dirname\(__file__\)\)\)",
        "os.path.dirname(os.path.dirname(__file__))",
        content
    )
    
    if content != fixed:
        with open(test_file, 'w', encoding='utf-8') as f:
            f.write(fixed)
        print(f"Fixed: {test_file}")

print("\nDone!")
