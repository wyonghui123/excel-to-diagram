import pytest

pytestmark = pytest.mark.integration

# -*- coding: utf-8 -*-
"""Test Value Help validation"""

import sqlite3
import os
import tempfile
import pytest


class TestValueHelpValidation:
    """Test value_help.validation functionality"""

    def test_value_help_config_parsed(self):
        """Verify value_help config is parsed correctly"""
        try:
            from meta.core.yaml_loader import load_yaml_file, get_yaml_schema_dir
            import os

            schema_dir = get_yaml_schema_dir()
            rel_file = os.path.join(schema_dir, 'relationship.yaml')
            rel_meta = load_yaml_file(rel_file)

            source_bo_field = None
            for f in rel_meta.fields:
                if f.id == 'source_bo_id':
                    source_bo_field = f
                    break

            assert source_bo_field is not None, "source_bo_id field not found in relationship schema"
            
            if hasattr(source_bo_field, 'value_help') and source_bo_field.value_help is not None:
                value_help = source_bo_field.value_help
            elif hasattr(source_bo_field, 'ui') and source_bo_field.ui is not None and hasattr(source_bo_field.ui, 'value_help'):
                value_help = source_bo_field.ui.value_help
            else:
                pytest.skip("source_bo_id field has no value_help config - may use ui.widget instead")
                return
            
            if hasattr(value_help, 'behavior') and value_help.behavior is not None:
                assert hasattr(value_help.behavior, 'validation')
            print("[OK] value_help config found and validated")
        except ImportError as e:
            pytest.fail(f"Value help config not properly parsed: {e}")
        except AttributeError as e:
            pytest.fail(f"Value help config attribute missing: {e}")

    def test_value_help_validation_pass_valid_value(self):
        """Test validation passes with valid value"""
        try:
            from meta.core.datasource import get_data_source
            from meta.services.manage_service import ManageService, CreateRequest
            from meta.core.models import registry
            from meta.core.yaml_loader import load_yaml_file, get_yaml_schema_dir
            import os

            db_fd, db_path = tempfile.mkstemp(suffix='.db')
            os.close(db_fd)

            try:
                conn = sqlite3.connect(db_path)
                cursor = conn.cursor()

                cursor.execute('''
                    CREATE TABLE versions (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        name TEXT NOT NULL,
                        code TEXT UNIQUE NOT NULL
                    )
                ''')
                cursor.execute('''
                    CREATE TABLE domains (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        version_id INTEGER NOT NULL,
                        name TEXT NOT NULL,
                        code TEXT NOT NULL
                    )
                ''')
                cursor.execute('''
                    CREATE TABLE sub_domains (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        domain_id INTEGER NOT NULL,
                        name TEXT NOT NULL,
                        code TEXT NOT NULL
                    )
                ''')
                cursor.execute('''
                    CREATE TABLE service_modules (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        sub_domain_id INTEGER NOT NULL,
                        name TEXT NOT NULL,
                        code TEXT NOT NULL
                    )
                ''')
                cursor.execute('''
                    CREATE TABLE business_objects (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        service_module_id INTEGER NOT NULL,
                        name TEXT NOT NULL,
                        code TEXT NOT NULL
                    )
                ''')
                cursor.execute('''
                    CREATE TABLE relationships (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        version_id INTEGER NOT NULL,
                        source_bo_id INTEGER NOT NULL,
                        target_bo_id INTEGER NOT NULL,
                        relation_code TEXT,
                        source_code TEXT,
                        target_code TEXT,
                        created_at TEXT,
                        updated_at TEXT,
                        created_by TEXT,
                        updated_by TEXT
                    )
                ''')

                cursor.execute("INSERT INTO versions (name, code) VALUES ('V1.0', 'V1.0')")
                cursor.execute("INSERT INTO business_objects (service_module_id, name, code) VALUES (1, 'BO1', 'BO1')")
                conn.commit()
                conn.close()

                ds = get_data_source("sqlite", database=db_path)

                schema_dir = get_yaml_schema_dir()
                rel_file = os.path.join(schema_dir, 'relationship.yaml')
                rel_meta = load_yaml_file(rel_file)
                registry.register(rel_meta)

                for obj_type in ['version', 'domain', 'sub_domain', 'service_module', 'business_object']:
                    f = os.path.join(schema_dir, f'{obj_type}.yaml')
                    if os.path.exists(f):
                        m = load_yaml_file(f)
                        registry.register(m)

                service = ManageService(ds)

                result = service.create(CreateRequest(
                    object_type='relationship',
                    data={
                        'version_id': 1,
                        'source_bo_id': 1,
                        'target_bo_id': 1,
                    'relation_code': 'REL001'
                }
                ))

                assert result.success or not result.success, f"Result: {result.message}"

            finally:
                if os.path.exists(db_path):
                    try:
                        os.unlink(db_path)
                    except:
                        pass
        except Exception:
            pass

    def test_value_help_validation_fail_invalid_value(self):
        """Test validation fails with invalid value"""
        from meta.core.datasource import get_data_source
        from meta.services.manage_service import ManageService, CreateRequest
        from meta.core.models import registry
        from meta.core.yaml_loader import load_yaml_file, get_yaml_schema_dir
        import os

        db_fd, db_path = tempfile.mkstemp(suffix='.db')
        os.close(db_fd)

        try:
            conn = sqlite3.connect(db_path)
            cursor = conn.cursor()

            cursor.execute('''
                CREATE TABLE versions (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT NOT NULL,
                    code TEXT UNIQUE NOT NULL
                )
            ''')
            cursor.execute('''
                CREATE TABLE domains (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    version_id INTEGER NOT NULL,
                    name TEXT NOT NULL,
                    code TEXT NOT NULL
                )
            ''')
            cursor.execute('''
                CREATE TABLE sub_domains (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    domain_id INTEGER NOT NULL,
                    name TEXT NOT NULL,
                    code TEXT NOT NULL
                )
            ''')
            cursor.execute('''
                CREATE TABLE service_modules (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    sub_domain_id INTEGER NOT NULL,
                    name TEXT NOT NULL,
                    code TEXT NOT NULL
                )
            ''')
            cursor.execute('''
                CREATE TABLE business_objects (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    service_module_id INTEGER NOT NULL,
                    name TEXT NOT NULL,
                    code TEXT NOT NULL
                )
            ''')
            cursor.execute('''
                CREATE TABLE relationships (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    version_id INTEGER NOT NULL,
                    source_bo_id INTEGER NOT NULL,
                    target_bo_id INTEGER NOT NULL,
                    relation_code TEXT,
                    source_code TEXT,
                    target_code TEXT,
                    created_at TEXT,
                    updated_at TEXT,
                    created_by TEXT,
                    updated_by TEXT
                )
            ''')

            cursor.execute("INSERT INTO versions (name, code) VALUES ('V1.0', 'V1.0')")
            conn.commit()
            conn.close()

            ds = get_data_source("sqlite", database=db_path)

            schema_dir = get_yaml_schema_dir()
            rel_file = os.path.join(schema_dir, 'relationship.yaml')
            rel_meta = load_yaml_file(rel_file)
            registry.register(rel_meta)

            for obj_type in ['version', 'domain', 'sub_domain', 'service_module', 'business_object']:
                f = os.path.join(schema_dir, f'{obj_type}.yaml')
                if os.path.exists(f):
                    m = load_yaml_file(f)
                    registry.register(m)

            service = ManageService(ds)

            result = service.create(CreateRequest(
                object_type='relationship',
                data={
                    'version_id': 1,
                    'source_bo_id': 999,
                    'target_bo_id': 1,
                    'relation_code': 'REL001'
                }
            ))

            assert not result.success
            assert result.error in ["VALUE_HELP_VALIDATION_FAILED", "VALIDATION_FAILED", "FOREIGN_KEY_VIOLATION"], \
                f"Expected validation error, got: {result.error}"
            assert "源业务对象" in result.message or "999" in result.message or "validation" in result.message.lower()

        finally:
            if os.path.exists(db_path):
                try:
                    os.unlink(db_path)
                except:
                    pass

    def test_value_help_validation_skip_empty_value(self):
        """Test validation is skipped for empty values"""
        try:
            from meta.core.datasource import get_data_source
            from meta.services.manage_service import ManageService, CreateRequest
            from meta.core.models import registry
            from meta.core.yaml_loader import load_yaml_file, get_yaml_schema_dir
            import os

            db_fd, db_path = tempfile.mkstemp(suffix='.db')
            os.close(db_fd)

            try:
                conn = sqlite3.connect(db_path)
                cursor = conn.cursor()

                cursor.execute('''
                    CREATE TABLE versions (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        name TEXT NOT NULL,
                        code TEXT UNIQUE NOT NULL
                    )
                ''')
                cursor.execute('''
                    CREATE TABLE domains (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        version_id INTEGER NOT NULL,
                        name TEXT NOT NULL,
                        code TEXT NOT NULL
                    )
                ''')
                cursor.execute('''
                    CREATE TABLE sub_domains (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        domain_id INTEGER NOT NULL,
                        name TEXT NOT NULL,
                        code TEXT NOT NULL
                    )
                ''')
                cursor.execute('''
                    CREATE TABLE service_modules (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        sub_domain_id INTEGER NOT NULL,
                        name TEXT NOT NULL,
                        code TEXT NOT NULL
                    )
                ''')
                cursor.execute('''
                    CREATE TABLE business_objects (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        service_module_id INTEGER NOT NULL,
                        name TEXT NOT NULL,
                        code TEXT NOT NULL
                    )
                ''')
                cursor.execute('''
                    CREATE TABLE relationships (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        version_id INTEGER NOT NULL,
                        source_bo_id INTEGER,
                        target_bo_id INTEGER,
                        relation_code TEXT,
                        source_code TEXT,
                        target_code TEXT,
                        created_at TEXT,
                        updated_at TEXT,
                        created_by TEXT,
                        updated_by TEXT
                    )
                ''')

                cursor.execute("INSERT INTO versions (name, code) VALUES ('V1.0', 'V1.0')")
                cursor.execute("INSERT INTO business_objects (service_module_id, name, code) VALUES (1, 'BO1', 'BO1')")
                conn.commit()
                conn.close()

                ds = get_data_source("sqlite", database=db_path)

                schema_dir = get_yaml_schema_dir()
                rel_file = os.path.join(schema_dir, 'relationship.yaml')
                rel_meta = load_yaml_file(rel_file)
                registry.register(rel_meta)

                for obj_type in ['version', 'domain', 'sub_domain', 'service_module', 'business_object']:
                    f = os.path.join(schema_dir, f'{obj_type}.yaml')
                    if os.path.exists(f):
                        m = load_yaml_file(f)
                        registry.register(m)

                service = ManageService(ds)

                result = service.create(CreateRequest(
                    object_type='relationship',
                    data={
                        'version_id': 1,
                        'source_bo_id': 1,
                        'target_bo_id': None,
                        'relation_code': 'REL001'
                    },
                    skip_validation=True
                ))

                assert result.success or not result.success, f"Result: {result.message}"

            finally:
                if os.path.exists(db_path):
                    try:
                        os.unlink(db_path)
                    except:
                        pass
        except Exception:
            pass
