import os

schemas = 'd:/filework/excel-to-diagram/meta/schemas'
for f in os.listdir(schemas):
    if 'product' in f.lower():
        print(f)
