# -*- coding: utf-8 -*-
import sqlite3
import os

db_path = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'meta', 'architecture.db'))
print('DB:', db_path)

db = sqlite3.connect(db_path)
db.row_factory = sqlite3.Row

# Test 1: count groups with <= 1 members
print('=== Test 1: COUNT with subquery <= 1 ===')
sql1 = "SELECT COUNT(*) as cnt FROM user_groups WHERE ((SELECT COUNT(*) FROM user_group_members WHERE user_group_members.group_id = user_groups.id) <= 1)"
row = db.execute(sql1).fetchone()
print('  result:', dict(row))

# Test 2: count groups with = 5 members
print('=== Test 2: COUNT with subquery = 5 ===')
sql2 = "SELECT COUNT(*) as cnt FROM user_groups WHERE ((SELECT COUNT(*) FROM user_group_members WHERE user_group_members.group_id = user_groups.id) = 5)"
row = db.execute(sql2).fetchone()
print('  result:', dict(row))

# Test 3: parameterized
print('=== Test 3: COUNT with subquery <= ? (param=1) ===')
sql3 = "SELECT COUNT(*) as cnt FROM user_groups WHERE ((SELECT COUNT(*) FROM user_group_members WHERE user_group_members.group_id = user_groups.id) <= ?)"
row = db.execute(sql3, [1]).fetchone()
print('  result:', dict(row))

# Test 4: total
print('=== Test 4: total user_groups ===')
row = db.execute("SELECT COUNT(*) as cnt FROM user_groups").fetchone()
print('  result:', dict(row))

# Test 5: distribution
print('=== Test 5: distribution of member_count ===')
sql5 = "SELECT (SELECT COUNT(*) FROM user_group_members WHERE user_group_members.group_id = user_groups.id) AS mc, COUNT(*) as cnt FROM user_groups GROUP BY mc ORDER BY mc"
for r in db.execute(sql5).fetchall():
    print('  ', dict(r))
