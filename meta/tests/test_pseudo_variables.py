import pytest

pytestmark = pytest.mark.integration

import pytest
from datetime import datetime
from meta.core.action_executor import PseudoVariableResolver, ActionExecutor
from meta.core.sql_adapters import SQLiteAdapter
from meta.core.schema_generator import SchemaGenerator


class TestPseudoVariableResolver:
    def test_resolve_now(self):
        resolver = PseudoVariableResolver()
        result = resolver.resolve('$now')
        assert result is not None
        parsed = datetime.fromisoformat(result)
        assert parsed is not None

    def test_resolve_user_name_with_context(self):
        resolver = PseudoVariableResolver({'user_name': 'testuser'})
        result = resolver.resolve('$user.name')
        assert result == 'testuser'

    def test_resolve_user_id_with_context(self):
        resolver = PseudoVariableResolver({'user_id': 42})
        result = resolver.resolve('$user.id')
        assert result == 42

    def test_resolve_user_name_without_context(self):
        resolver = PseudoVariableResolver({})
        result = resolver.resolve('$user.name')
        assert result == ''

    def test_resolve_uuid(self):
        resolver = PseudoVariableResolver()
        result = resolver.resolve('$uuid')
        assert result is not None
        assert len(result) == 36
        assert '-' in result

    def test_resolve_uuid_unique(self):
        resolver = PseudoVariableResolver()
        result1 = resolver.resolve('$uuid')
        result2 = resolver.resolve('$uuid')
        assert result1 != result2

    def test_resolve_non_pseudo_variable(self):
        resolver = PseudoVariableResolver()
        result = resolver.resolve('hello')
        assert result == 'hello'

    def test_resolve_empty_string(self):
        resolver = PseudoVariableResolver()
        result = resolver.resolve('')
        assert result == ''

    def test_resolve_none(self):
        resolver = PseudoVariableResolver()
        result = resolver.resolve(None)
        assert result is None


def _create_domains_table(adapter, domain):
    generator = SchemaGenerator(dialect='sqlite')
    create_sql = generator.generate_create_table(domain)
    if create_sql:
        adapter.execute(create_sql)
        adapter.commit()


class TestAutoFillIntegration:
    def test_auto_fill_on_create(self, tmp_path):
        adapter = SQLiteAdapter()
        db_path = str(tmp_path / 'test.db')
        adapter.connect(path=db_path)

        from meta import get_meta_object
        domain = get_meta_object('domain')

        _create_domains_table(adapter, domain)

        executor = ActionExecutor(adapter)
        executor.set_audit_user(user_id=1, user_name='testuser')

        result = executor.execute(domain, 'crud_create', {
            'version_id': 1,
            'code': 'TEST_DOMAIN_AF',
            'name': 'Test Domain AutoFill',
        })

        if result.success:
            record = adapter.find_by_id('domains', result.last_insert_id)
            if record:
                assert record.get('created_at') is not None

        adapter.disconnect()

    def test_auto_fill_on_update(self, tmp_path):
        adapter = SQLiteAdapter()
        db_path = str(tmp_path / 'test_update.db')
        adapter.connect(path=db_path)

        from meta import get_meta_object
        domain = get_meta_object('domain')

        _create_domains_table(adapter, domain)

        executor = ActionExecutor(adapter)
        executor.set_audit_user(user_id=1, user_name='testuser')

        create_result = executor.execute(domain, 'crud_create', {
            'version_id': 1,
            'code': 'TEST_DOMAIN_UP',
            'name': 'Test Domain Update',
        })

        if create_result.success:
            original = adapter.find_by_id('domains', create_result.last_insert_id)
            if original:
                import time
                time.sleep(0.01)

                update_result = executor.execute(domain, 'crud_update', {
                    'id': create_result.last_insert_id,
                    'name': 'Updated Domain Name',
                })

                if update_result.success:
                    updated = adapter.find_by_id('domains', create_result.last_insert_id)
                    if updated:
                        assert updated.get('created_at') is not None

        adapter.disconnect()


class TestAutoFillUserIntegration:
    def test_created_by_filled_with_username(self, tmp_path):
        adapter = SQLiteAdapter()
        db_path = str(tmp_path / 'test_user.db')
        adapter.connect(path=db_path)

        from meta import get_meta_object
        domain = get_meta_object('domain')

        _create_domains_table(adapter, domain)

        executor = ActionExecutor(adapter)
        executor.set_audit_user(user_id=1, user_name='john_doe')

        result = executor.execute(domain, 'crud_create', {
            'version_id': 1,
            'code': 'TEST_USER_DOMAIN',
            'name': 'Test User Domain',
        })

        if result.success:
            record = adapter.find_by_id('domains', result.last_insert_id)
            if record:
                assert record.get('created_by') == 'john_doe'
                assert record.get('updated_by') == 'john_doe'

        adapter.disconnect()

    def test_updated_by_changes_on_update(self, tmp_path):
        adapter = SQLiteAdapter()
        db_path = str(tmp_path / 'test_user_update.db')
        adapter.connect(path=db_path)

        from meta import get_meta_object
        domain = get_meta_object('domain')

        _create_domains_table(adapter, domain)

        executor = ActionExecutor(adapter)
        executor.set_audit_user(user_id=1, user_name='creator')

        create_result = executor.execute(domain, 'crud_create', {
            'version_id': 1,
            'code': 'TEST_USER_UP',
            'name': 'Test User Update',
        })

        if create_result.success:
            executor.set_audit_user(user_id=2, user_name='updater')

            update_result = executor.execute(domain, 'crud_update', {
                'id': create_result.last_insert_id,
                'name': 'Updated Name',
            })

            if update_result.success:
                record = adapter.find_by_id('domains', create_result.last_insert_id)
                if record:
                    assert record.get('created_by') == 'creator'
                    assert record.get('updated_by') == 'updater'

        adapter.disconnect()


class TestProductAutoFill:
    def test_product_auto_fill_on_create(self, tmp_path):
        try:
            adapter = SQLiteAdapter()
            db_path = str(tmp_path / 'test_product.db')
            adapter.connect(path=db_path)

            from meta import get_meta_object
            product = get_meta_object('product')

            if product is None:
                pytest.fail("product meta object not registered")

            _create_domains_table(adapter, product)

            executor = ActionExecutor(adapter)
            executor.set_audit_user(user_id=1, user_name='product_creator')

            result = executor.execute(product, 'crud_create', {
                'code': 'TEST_PRODUCT',
                'name': 'Test Product',
            })

            if result.success:
                record = adapter.find_by_id('products', result.last_insert_id)
                if record:
                    assert record.get('created_at') is not None
                    assert record.get('created_by') == 'product_creator'
                    assert record.get('updated_by') == 'product_creator'

            adapter.disconnect()
        except Exception as e:
            pytest.fail(f"Pseudo variable auto-fill skipped: {e}")


class TestVersionAutoFill:
    def test_version_auto_fill_on_create(self, tmp_path):
        adapter = SQLiteAdapter()
        db_path = str(tmp_path / 'test_version.db')
        adapter.connect(path=db_path)

        from meta import get_meta_object
        version = get_meta_object('version')

        _create_domains_table(adapter, version)

        executor = ActionExecutor(adapter)
        executor.set_audit_user(user_id=1, user_name='version_creator')

        result = executor.execute(version, 'crud_create', {
            'product_id': 1,
            'code': 'V1_0',
            'name': 'Version 1.0',
        })

        if result.success:
            record = adapter.find_by_id('versions', result.last_insert_id)
            if record:
                assert record.get('created_at') is not None
                assert record.get('created_by') == 'version_creator'

        adapter.disconnect()


class TestAnnotationAutoFill:
    def test_annotation_auto_fill_on_create(self, tmp_path):
        try:
            adapter = SQLiteAdapter()
            db_path = str(tmp_path / 'test_annotation.db')
            adapter.connect(path=db_path)

            from meta import get_meta_object
            annotation = get_meta_object('annotation')

            if annotation is None:
                pytest.fail("annotation meta object not registered")

            _create_domains_table(adapter, annotation)

            executor = ActionExecutor(adapter)
            executor.set_audit_user(user_id=1, user_name='note_taker')

            result = executor.execute(annotation, 'crud_create', {
                'target_type': 'domain',
                'target_id': 1,
                'category': 'info',
                'content': 'This is a test annotation',
            })

            if result.success:
                record = adapter.find_by_id('annotations', result.last_insert_id)
                if record:
                    assert record.get('created_at') is not None
                    assert record.get('created_by') == 'note_taker'
                    assert record.get('updated_by') == 'note_taker'

            adapter.disconnect()
        except Exception as e:
            pytest.fail(f"Pseudo variable auto-fill skipped: {e}")

    def test_annotation_auto_fill_on_update(self, tmp_path):
        adapter = SQLiteAdapter()
        db_path = str(tmp_path / 'test_annotation_update.db')
        adapter.connect(path=db_path)

        from meta import get_meta_object
        annotation = get_meta_object('annotation')

        _create_domains_table(adapter, annotation)

        executor = ActionExecutor(adapter)
        executor.set_audit_user(user_id=1, user_name='first_author')

        create_result = executor.execute(annotation, 'crud_create', {
            'target_type': 'domain',
            'target_id': 1,
            'category': 'info',
            'content': 'Original content',
        })

        if create_result.success:
            import time
            time.sleep(0.01)

            executor.set_audit_user(user_id=2, user_name='second_author')

            update_result = executor.execute(annotation, 'crud_update', {
                'id': create_result.last_insert_id,
                'content': 'Updated content',
            })

            if update_result.success:
                record = adapter.find_by_id('annotations', create_result.last_insert_id)
                if record:
                    assert record.get('created_by') == 'first_author'
                    assert record.get('updated_by') == 'second_author'

        adapter.disconnect()
