"""Test BatchAuditContext - FR-LOG-007"""
import pytest
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


class TestBatchAuditContext:
    """FR-LOG-007: 1 header + N details (Stripe batch events 模式)"""

    def test_creates_header_on_enter(self):
        from meta.services.audit_service import BatchAuditContext, AuditRecord

        class MockAudit:
            def __init__(self):
                self.created = []
            def create(self, rec):
                rec.id = len(self.created) + 1
                self.created.append(rec)
                return rec.id
            def update(self, id, **kwargs):
                for r in self.created:
                    if r.id == id:
                        for k, v in kwargs.items():
                            setattr(r, k, v)
                        return True
                return False

        audit = MockAudit()
        with BatchAuditContext(
            action='batch_create_users',
            object_type='user',
            audit_service=audit,
            user_context={'user_id': 1, 'user_name': 'alice'},
        ) as batch:
            assert batch.header_id is not None
            assert len(audit.created) == 1  # header

        # header 应是 static + batch 标记
        header = audit.created[0]
        assert header.action_kind == 'static'
        assert header.object_id == 'batch'
        assert header.action == 'batch_create_users'
        assert header.outcome == 'success'

    def test_add_detail_creates_with_parent_id(self):
        from meta.services.audit_service import BatchAuditContext

        class MockAudit:
            def __init__(self):
                self.created = []
            def create(self, rec):
                rec.id = len(self.created) + 1
                self.created.append(rec)
                return rec.id
            def update(self, *args, **kwargs):
                return False

        audit = MockAudit()
        with BatchAuditContext(
            action='batch_create_users',
            object_type='user',
            audit_service=audit,
            user_context={'user_id': 1},
        ) as batch:
            batch.add_detail(object_id=101, outcome='success')
            batch.add_detail(object_id=102, outcome='success')
            batch.add_detail(object_id=103, outcome='failure', error_msg='duplicate')

        assert len(audit.created) == 1 + 3  # 1 header + 3 details

        # 验证 detail 关联
        details = audit.created[1:]
        assert details[0].parent_action_id == batch.header_id
        assert details[0].action_kind == 'instance'
        assert details[0].action == 'create_users'  # batch_ prefix 去掉
        assert details[0].object_id == 101
        assert details[0].outcome == 'success'

        assert details[2].outcome == 'failure'
        assert details[2].error_message == 'duplicate'

    def test_exception_updates_header_outcome(self):
        """batch 整体失败 → header outcome 改为 failure"""
        from meta.services.audit_service import BatchAuditContext

        class MockAudit:
            def __init__(self):
                self.created = []
                self.updates = []
            def create(self, rec):
                rec.id = len(self.created) + 1
                self.created.append(rec)
                return rec.id
            def update(self, id, **kwargs):
                self.updates.append((id, kwargs))
                return True

        audit = MockAudit()
        with pytest.raises(RuntimeError, match="batch_failed"):
            with BatchAuditContext(
                action='batch_create_users',
                object_type='user',
                audit_service=audit,
                user_context={'user_id': 1},
            ) as batch:
                raise RuntimeError("batch_failed")

        # header 被更新为 failure
        assert len(audit.updates) == 1
        update_id, update_kwargs = audit.updates[0]
        assert update_kwargs['outcome'] == 'failure'
        assert 'batch_failed' in update_kwargs['error_message']

    def test_header_create_failure_does_not_block_main(self):
        """header 创建失败不影响主流程"""
        from meta.services.audit_service import BatchAuditContext

        class FailingAudit:
            def create(self, rec):
                raise RuntimeError("DB down")
            def update(self, *args, **kwargs):
                return False

        audit = FailingAudit()
        # 即使 header 创建失败，with 块也应正常进入
        with BatchAuditContext(
            action='batch_op',
            object_type='user',
            audit_service=audit,
            user_context={'user_id': 1},
        ) as batch:
            # header_id 应为 None（创建失败）
            assert batch.header_id is None
            # add_detail 也应不抛错
            batch.add_detail(object_id=1, outcome='success')
            # batch.details_count 应为 1
            assert batch.details_count == 1

    def test_no_exception_keeps_header_outcome_success(self):
        """无异常时 header 保持 success"""
        from meta.services.audit_service import BatchAuditContext

        class MockAudit:
            def __init__(self):
                self.created = []
                self.updates = []
            def create(self, rec):
                rec.id = len(self.created) + 1
                self.created.append(rec)
                return rec.id
            def update(self, *args, **kwargs):
                self.updates.append((args, kwargs))
                return True

        audit = MockAudit()
        with BatchAuditContext(
            action='batch_op',
            object_type='user',
            audit_service=audit,
            user_context={'user_id': 1},
        ):
            pass

        # 没有异常 → 不调用 update
        assert len(audit.updates) == 0
        assert audit.created[0].outcome == 'success'


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
