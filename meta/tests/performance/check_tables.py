# -*- coding: utf-8 -*-
import tempfile
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from meta.core.datasource import get_data_source
from meta.core.schema_generator import sync_schema_from_meta
from meta.core.models import registry
from meta.core.index_management_service import IndexManagementService

with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
    db_path = f.name

try:
    ds = get_data_source("sqlite", database=db_path)
    meta_objects = [registry.get(obj_id) for obj_id in registry.list_objects()]
    sync_schema_from_meta(ds, meta_objects)
    
    service = IndexManagementService(ds)
    service.create_all_indexes()
    
    now = int(time.time())
    
    print("Inserting product...")
    ds.execute("""
        INSERT INTO products (id, name, code, description, created_at, updated_at)
        VALUES (?, ?, ?, ?, ?, ?)
    """, (1, "产品1", "PRD001", "产品描述1", now, now))
    
    print("Inserting version...")
    ds.execute("""
        INSERT INTO versions (id, name, code, product_id, created_at, updated_at)
        VALUES (?, ?, ?, ?, ?, ?)
    """, (1, "版本1", "V01", 1, now, now))
    
    print("Inserting domain...")
    ds.execute("""
        INSERT INTO domains (id, name, code, version_id, created_at, updated_at)
        VALUES (?, ?, ?, ?, ?, ?)
    """, (1, "领域1", "DOM001", 1, now, now))
    
    print("Inserting business objects...")
    batch_data = [
        ("业务对象{0}".format(i), "BO{0:05d}".format(i), "描述{0}".format(i), 1, 1, now, now)
        for i in range(100)
    ]
    ds.execute_batch("""
        INSERT INTO business_objects 
        (name, code, description, version_id, domain_id, created_at, updated_at)
        VALUES (?, ?, ?, ?, ?, ?, ?)
    """, batch_data)
    
    ds.commit()
    
    count = ds.query_one("SELECT COUNT(*) as cnt FROM business_objects")
    print("Business objects count:", count["cnt"])
    
    ds.disconnect()
    print("SUCCESS!")
finally:
    try:
        os.remove(db_path)
    except Exception as e:
        print("Cleanup error:", e)
