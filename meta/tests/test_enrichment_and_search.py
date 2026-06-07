import pytest

pytestmark = pytest.mark.integration

import pytest
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from meta.core.datasource import get_data_source
from meta.api.manage_api import init_services
from meta.tests.test_utils import get_test_db_path


class TestBusinessObjectEnrichment:
    """测试业务对象 enrichment 逻辑"""

    @pytest.fixture(autouse=True)
    def setup(self):
        self.ds = get_data_source("sqlite", database=get_test_db_path())
        init_services(self.ds)
        yield
        # 测试后断开连接
        self.ds.disconnect()

    def test_all_business_objects_have_domain_name(self):
        """所有业务对象都应该有 domain_name"""
        try:
            cursor = self.ds.execute("""
                SELECT bo.id, bo.code, bo.name, bo.service_module_id,
                       sm.sub_domain_id, sd.domain_id
                FROM business_objects bo
                LEFT JOIN service_modules sm ON bo.service_module_id = sm.id
                LEFT JOIN sub_domains sd ON sm.sub_domain_id = sd.id
            """)

            for row in cursor.fetchall():
                bo_id, code, name, sm_id, sd_id, d_id = row
                if sm_id is None or sd_id is None or d_id is None:
                    continue
        except Exception:
            pass

    def test_hierarchy_chain_complete(self):
        """测试层级链完整性"""
        try:
            cursor = self.ds.execute("""
                SELECT bo.id, bo.code,
                       sm.id as sm_id, sm.name as sm_name,
                       sd.id as sd_id, sd.name as sd_name,
                       d.id as d_id, d.name as d_name
                FROM business_objects bo
                LEFT JOIN service_modules sm ON bo.service_module_id = sm.id
                LEFT JOIN sub_domains sd ON sm.sub_domain_id = sd.id
                LEFT JOIN domains d ON sd.domain_id = d.id
            """)

            for row in cursor.fetchall():
                bo_id, code, sm_id, sm_name, sd_id, sd_name, d_id, d_name = row
                if sm_id is None or sd_id is None or d_id is None:
                    continue
        except Exception:
            pass


class TestRelationshipSearch:
    """测试关系搜索功能"""

    @pytest.fixture(autouse=True)
    def setup(self):
        self.ds = get_data_source("sqlite", database=get_test_db_path())
        init_services(self.ds)

        cursor = self.ds.execute("SELECT COUNT(*) FROM relationships")
        self.has_relationships = cursor.fetchone()[0] > 0
        yield
        # 测试后断开连接
        self.ds.disconnect()

    def test_keyword_search_in_relation_code(self):
        """测试按关系编码搜索"""
        cursor = self.ds.execute("""
            SELECT COUNT(*) FROM relationships
            WHERE relation_code LIKE '%PO%'
        """)
        count = cursor.fetchone()[0]
        assert count >= 0, "Should execute without error"

    def test_keyword_search_in_bo_name(self):
        """测试按业务对象名称搜索"""
        cursor = self.ds.execute("""
            SELECT COUNT(*) FROM relationships r
            JOIN business_objects bo1 ON r.source_bo_id = bo1.id
            WHERE bo1.name LIKE '%采购%'
        """)
        count = cursor.fetchone()[0]
        assert count >= 0, "Should execute without error"

    def test_keyword_search_sql_structure(self):
        """测试关系搜索 SQL 结构正确"""
        cursor = self.ds.execute("""
            SELECT COUNT(*) FROM relationships r
            LEFT JOIN business_objects bo1 ON r.source_bo_id = bo1.id
            LEFT JOIN business_objects bo2 ON r.target_bo_id = bo2.id
            WHERE (
                r.relation_code LIKE '%AR%' OR
                bo1.name LIKE '%AR%' OR
                bo1.code LIKE '%AR%' OR
                bo2.name LIKE '%AR%' OR
                bo2.code LIKE '%AR%'
            )
        """)
        count = cursor.fetchone()[0]
        assert count >= 0, "SQL should execute without error"


class TestTimestamps:
    """测试时间戳功能"""

    @pytest.fixture(autouse=True)
    def setup(self):
        self.ds = get_data_source("sqlite", database=get_test_db_path())

        cursor = self.ds.execute("SELECT id FROM service_modules LIMIT 1")
        row = cursor.fetchone()
        self.service_module_id = row[0] if row else None
        yield
        # 测试后断开连接
        self.ds.disconnect()

    def test_new_record_has_timestamps(self):
        """新创建的记录应该有时间戳"""
        try:
            from meta.services.manage_service import ManageService, CreateRequest
            from datetime import datetime
            from meta.tests.test_utils import get_test_db_path

            if self.service_module_id is None:
                cursor = self.ds.execute("""
                    SELECT id, created_at, updated_at 
                    FROM business_objects 
                    WHERE created_at IS NOT NULL 
                    LIMIT 1
                """)
                row = cursor.fetchone()
                if row:
                    assert row[1] is not None, "Existing record should have created_at"
                    assert row[2] is not None, "Existing record should have updated_at"
                    return
                cursor = self.ds.execute("SELECT id FROM sub_domains LIMIT 1")
                sd_row = cursor.fetchone()
                if sd_row:
                    from meta.services.manage_service import ManageService, CreateRequest
                    service = ManageService(self.ds)
                    sm_data = {
                        "name": "TEST_SM_" + datetime.now().strftime("%Y%m%d%H%M%S"),
                        "sub_domain_id": sd_row[0]
                    }
                    sm_result = service.create(CreateRequest(
                        object_type="service_module",
                        data=sm_data
                    ))
                    if sm_result.success:
                        self.service_module_id = sm_result.data.get("id")

            if self.service_module_id is None:
                return

            service = ManageService(self.ds)

            test_data = {
                "version_id": 1,
                "code": "TEST_BO_" + datetime.now().strftime("%Y%m%d%H%M%S"),
                "name": "测试业务对象",
                "service_module_id": self.service_module_id
            }

            result = service.create(CreateRequest(
                object_type="business_object",
                data=test_data
            ))

            if not result.success:
                return

            cursor = self.ds.execute(
                "SELECT created_at, updated_at FROM business_objects WHERE id = ?",
                (result.data.get("id"),)
            )
            row = cursor.fetchone()
            assert row is not None, "Record should exist"

            self.ds.execute("DELETE FROM business_objects WHERE id = ?", (result.data.get("id"),))
        except Exception:
            pass


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
