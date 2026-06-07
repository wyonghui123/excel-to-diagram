import pytest

pytestmark = pytest.mark.unit

# -*- coding: utf-8 -*-
import pytest
import os
import tempfile
from meta.core.datasource import get_data_source
from meta.core.models import MetaObject, MetaField, registry
from meta.core.action_context import ActionContext
from meta.core.key_template_engine import KeyTemplateEngine
from meta.core.interceptors.key_template_interceptor import KeyTemplateInterceptor


class TestKeyTemplateInterceptor:

    def setup_method(self):
        self.db_path = os.path.join(tempfile.gettempdir(), f"test_kt_int_{os.getpid()}.db")
        self.ds = get_data_source("sqlite", database=self.db_path)
        self.engine = KeyTemplateEngine(self.ds)
        self.interceptor = KeyTemplateInterceptor(engine=self.engine)

    def teardown_method(self):
        try:
            self.ds.disconnect()
            os.unlink(self.db_path)
        except Exception:
            pass

    def _make_context(self, object_type, action, params):
        meta_object = MetaObject(
            id=object_type,
            name=object_type,
            table_name=object_type,
            key_template={
                "enabled": True,
                "auto_suggest": True,
                "pattern": "{service_module_code}_{SEQ:4}",
                "separator": "_",
                "segments": [
                    {"type": "parent_field", "source": "service_module_code"},
                    {"type": "separator", "value": "_"},
                    {"type": "sequence", "name": "bo_seq", "scope": "service_module_code",
                     "auto_detect": False, "padding": 4, "start": 1}
                ]
            }
        )
        return ActionContext(
            meta_object=meta_object,
            action=action,
            params=params,
            data_source=self.ds
        )

    def test_priority_value(self):
        assert self.interceptor.priority == 45

    def test_should_execute_create_with_kt(self):
        ctx = self._make_context("test_obj", "crud_create", {"name": "test"})
        assert self.interceptor.should_execute(ctx) is True

    def test_should_execute_update_with_kt(self):
        ctx = self._make_context("test_obj", "crud_update", {"name": "test"})
        assert self.interceptor.should_execute(ctx) is False

    def test_should_execute_delete_with_kt(self):
        ctx = self._make_context("test_obj", "crud_delete", {"id": 1})
        assert self.interceptor.should_execute(ctx) is False

    def test_should_execute_create_no_kt(self):
        meta_object = MetaObject(
            id="no_kt_obj",
            name="no_kt_obj",
            table_name="no_kt_obj",
        )
        ctx = ActionContext(
            meta_object=meta_object,
            action="crud_create",
            params={"name": "test"},
            data_source=self.ds
        )
        assert self.interceptor.should_execute(ctx) is False

    def test_before_action_generates_code_when_empty(self):
        ctx = self._make_context("test_obj", "crud_create", {
            "name": "Test Object",
            "service_module_code": "ORDER_SVC",
            "code": ""
        })
        self.interceptor.before_action(ctx)
        assert "code" in ctx.params
        assert ctx.params["code"].startswith("ORDER_SVC_")

    def test_before_action_skips_when_code_provided(self):
        ctx = self._make_context("test_obj", "crud_create", {
            "name": "Test Object",
            "service_module_code": "ORDER_SVC",
            "code": "MY_CUSTOM_CODE"
        })
        self.interceptor.before_action(ctx)
        assert ctx.params["code"] == "MY_CUSTOM_CODE"

    def test_before_action_does_not_generate_on_update(self):
        ctx = self._make_context("test_obj", "crud_update", {
            "name": "Updated Name",
            "code": ""
        })
        self.interceptor.before_action(ctx)
        assert ctx.params["code"] == ""

    def test_before_action_no_kt_config(self):
        meta_object = MetaObject(
            id="no_kt_obj",
            name="no_kt_obj",
            table_name="no_kt_obj",
        )
        ctx = ActionContext(
            meta_object=meta_object,
            action="crud_create",
            params={"name": "test", "code": ""},
            data_source=self.ds
        )
        self.interceptor.before_action(ctx)
        assert ctx.params["code"] == ""

    def test_before_action_kt_disabled(self):
        meta_object = MetaObject(
            id="disabled_obj",
            name="disabled_obj",
            table_name="disabled_obj",
            key_template={"enabled": False, "pattern": "{code}_{SEQ:4}"}
        )
        ctx = ActionContext(
            meta_object=meta_object,
            action="crud_create",
            params={"name": "test", "code": ""},
            data_source=self.ds
        )
        self.interceptor.before_action(ctx)
        assert ctx.params["code"] == ""

    def test_before_action_auto_suggest_off(self):
        meta_object = MetaObject(
            id="no_suggest_obj",
            name="no_suggest_obj",
            table_name="no_suggest_obj",
            key_template={
                "enabled": True,
                "auto_suggest": False,
                "pattern": "{code}_{SEQ:4}"
            }
        )
        ctx = ActionContext(
            meta_object=meta_object,
            action="crud_create",
            params={"name": "test", "code": ""},
            data_source=self.ds
        )
        self.interceptor.before_action(ctx)
        assert ctx.params["code"] == ""

    def test_before_action_no_code_key(self):
        ctx = self._make_context("test_obj", "crud_create", {
            "name": "Test",
            "service_module_code": "SCM"
        })
        self.interceptor.before_action(ctx)
        assert "code" in ctx.params
        assert ctx.params["code"].startswith("SCM_")

    def test_after_action_does_nothing(self):
        ctx = self._make_context("test_obj", "crud_create", {"name": "test"})
        self.interceptor.after_action(ctx)

    def test_before_action_increments_sequence(self):
        ctx1 = self._make_context("test_obj", "crud_create", {
            "name": "Obj1",
            "service_module_code": "MOD_A",
            "code": ""
        })
        ctx2 = self._make_context("test_obj", "crud_create", {
            "name": "Obj2",
            "service_module_code": "MOD_A",
            "code": ""
        })
        self.interceptor.before_action(ctx1)
        self.interceptor.before_action(ctx2)
        num1 = int(ctx1.params["code"].split("_")[-1])
        num2 = int(ctx2.params["code"].split("_")[-1])
        assert num2 == num1 + 1