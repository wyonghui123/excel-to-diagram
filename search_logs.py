import re

log_file = 'D:/filework/excel-to-diagram/meta/server.log'

try:
    with open(log_file, 'r', encoding='utf-8') as f:
        content = f.read()
    
    # 搜索 ASSOCIATE 相关的日志
    associate_logs = re.findall(r'.*associate.*', content, re.IGNORECASE)
    
    print(f"Found {len(associate_logs)} ASSOCIATE related logs:")
    for log in associate_logs[-20:]:
        print(log[:200])
        
except FileNotFoundError:
    print("Log file not found")
except Exception as e:
    print(f"Error: {e}")
