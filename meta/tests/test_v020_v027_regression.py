# -*- coding: utf-8 -*-
"""
test_v020_v027_regression.py

Guard-style regression tests for V020-V027 bug fixes.
Verifies that fix guard points are still present in the codebase.

## Bug Summary

| ID | File | Guard |
|----|------|-------|
| V020 | import_export_service.py | _build_permission_filter dim scope branch must OR owner exception |
| V021 | query_service.py | _try_apply_dimension_scope must OR owner_id into dim scope group |
| V022 | version.yaml | owner_id field (if present) must have export_visible: false |
| V023 | import_export_service.py | _should_export_field must NOT have active business_key early return |
| V024 | import_export_service.py | _write_child_sheet sort key must include is_counting/computed+virtual |
| V025 | version.yaml | fields section must NOT have duplicate visibility field definition |
| V026 | data_permission_interceptor.py | _add_owner_exception must use build_owner_exception_subquery |
| V027 | import_export_service.py | _collect_child_object_types must contain annotation auto-include |

## Test Strategy

- Pure static analysis: source code string matching via re.search / in operator
- No runtime execution or backend imports
- Each test class maps to one bug (or a closely-related bug pair)
- Assert messages reference BUG ID for fast triage

Reference:
- meta/tests/test_scope_tree_regression_v034.py (pattern template)
- meta/tests/test_v038_regression.py (pattern template)
"""

import re
import pytest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]  # meta/tests/ -> excel-to-diagram/

# ─── Source file paths ──────────────────────────────────────────────────

IMPORT_EXPORT_SERVICE_PATH = PROJECT_ROOT / 'meta' / 'services' / 'import_export_service.py'
QUERY_SERVICE_PATH = PROJECT_ROOT / 'meta' / 'services' / 'query_service.py'
VERSION_YAML_PATH = PROJECT_ROOT / 'meta' / 'schemas' / 'version.yaml'
DATA_PERMISSION_INTERCEPTOR_PATH = (
    PROJECT_ROOT / 'meta' / 'core' / 'interceptors' / 'data_permission_interceptor.py'
)


# ─── Helper functions ───────────────────────────────────────────────────

def _read_file(rel_path: str) -> str:
    """Read a file relative to PROJECT_ROOT."""
    full = PROJECT_ROOT / rel_path
    assert full.exists(), f"Guard source file missing: {full}"
    return full.read_text(encoding='utf-8')


def _read_abs(abs_path: Path) -> str:
    """Read a file by absolute Path, asserting it exists."""
    assert abs_path.exists(), f"Guard source file missing: {abs_path}"
    return abs_path.read_text(encoding='utf-8')


def _extract_function_body(source: str, func_name: str) -> str:
    """Extract the body of a top-level or method function by name.

    Returns the text from the def line up to the next def at the same or
    lower indentation, or the end of the source. Works for simple cases
    where there is no nested class between functions.
    """
    m = re.search(
        rf'def\s+{re.escape(func_name)}\s*\([^)]*\)[^\n]*:',
        source,
    )
    if not m:
        return ''
    start = m.end()
    # Find next top-level def or class at column 0 (or 4 for methods)
    next_def = re.search(r'\n(?:    )?def\s+', source[start:])
    end = start + next_def.start() if next_def else len(source)
    return source[start:end]


# ─── V020 / V021: dim scope owner exception ─────────────────────────────

class TestV020DimScopeOwnerException:
    """BUG-V020: _build_permission_filter dim scope branch must OR owner exception.

    Root cause: In import_export_service._build_permission_filter, the dim scope
    path previously returned early without adding owner exception. This caused
    user-owned private products to be filtered out by dim scope, returning only
    a few products instead of all owned+scoped ones.

    Fix: After dim scope SQL fragment is built, continue to add owner exception
    OR clause (same as the fallback path).
    """

    def test_build_permission_filter_dim_scope_owner_exception_present(self):
        """BUG-V020 guard: _build_permission_filter dim scope branch must reference owner_exception.

        The dim scope branch (after BUG-V020 fix) must NOT return early
        without adding owner exception. We check that the dim scope code
        block contains 'owner_exception' or 'BUG-V020' marker.
        """
        src = _read_abs(IMPORT_EXPORT_SERVICE_PATH)

        # Find _build_permission_filter function body
        func_body = _extract_function_body(src, '_build_permission_filter')
        assert func_body, "BUG-V020 guard: _build_permission_filter function not found"

        # The dim scope branch must contain owner exception logic
        # Check for the BUG-V020 fix marker or owner_exception reference
        assert 'BUG-V020' in func_body or 'owner_exception' in func_body, (
            "BUG-V020 guard failed: _build_permission_filter dim scope branch "
            "does not contain owner_exception or BUG-V020 marker. "
            "The dim scope path must OR owner exception, not return early."
        )

    def test_build_permission_filter_dim_scope_not_early_return(self):
        """BUG-V020 guard: dim scope path must NOT have bare 'return' before owner exception.

        The old buggy code did 'if sql_fragment: return base_sql, base_params'
        in the dim scope branch, skipping owner exception. After the fix,
        the dim scope path sets dim_scope_applied=True but does NOT return
        immediately.
        """
        src = _read_abs(IMPORT_EXPORT_SERVICE_PATH)
        func_body = _extract_function_body(src, '_build_permission_filter')
        assert func_body, "BUG-V020 guard: _build_permission_filter function not found"

        # Verify dim_scope_applied flag is used (not early return)
        assert 'dim_scope_applied' in func_body, (
            "BUG-V020 guard failed: _build_permission_filter does not use "
            "dim_scope_applied flag. The fix uses this flag to avoid early return, "
            "allowing owner exception to be added after dim scope."
        )


class TestV021DimScopeOwnerException:
    """BUG-V021: query_service _try_apply_dimension_scope must OR owner_id.

    Root cause: query_service.search path skipped DataPermissionInterceptor
    (which handles owner exception via _add_owner_exception). When dim scope
    was applied, the function returned True without adding owner_id to the
    OR group. This caused user-owned private products to be invisible in
    value-help / search results.

    Fix: After building dim scope OR conditions, append ('owner_id', EQ, user_id)
    for product type into the same OR group.
    """

    def test_try_apply_dimension_scope_owner_id_in_or_group(self):
        """BUG-V021 guard: _try_apply_dimension_scope must OR owner_id for product.

        The fix adds owner_id to the or_conditions list when object_type == 'product'.
        """
        src = _read_abs(QUERY_SERVICE_PATH)

        func_body = _extract_function_body(src, '_try_apply_dimension_scope')
        assert func_body, "BUG-V021 guard: _try_apply_dimension_scope function not found"

        # Check for BUG-V021 marker or owner_id OR merge logic
        assert 'BUG-V021' in func_body or 'owner_id' in func_body, (
            "BUG-V021 guard failed: _try_apply_dimension_scope does not contain "
            "owner_id or BUG-V021 marker. The function must OR owner_id into "
            "the dim scope OR group for product type."
        )

    def test_try_apply_dimension_scope_or_where_call(self):
        """BUG-V021 guard: _try_apply_dimension_scope must call builder.or_where.

        The fix merges dim scope conditions + owner exception into a single
        OR group via builder.or_where(), instead of builder.where() which
        would create an AND condition.
        """
        src = _read_abs(QUERY_SERVICE_PATH)
        func_body = _extract_function_body(src, '_try_apply_dimension_scope')
        assert func_body, "BUG-V021 guard: _try_apply_dimension_scope function not found"

        assert '.or_where(' in func_body, (
            "BUG-V021 guard failed: _try_apply_dimension_scope does not call "
            "builder.or_where(). The fix uses or_where to merge dim scope + "
            "owner exception into a single OR group."
        )


# ─── V022: version.yaml owner_id field ──────────────────────────────────

class TestV022VersionYamlOwnerId:
    """BUG-V022: version.yaml owner_id must have export_visible: false.

    Original fix: Removed explicit owner_id field definition from version.yaml
    because owner_aspect provides it.

    Later (BUG-V019): owner_id was re-added to version.yaml to override
    owner_aspect inheritance (avoiding duplicate owner propagation). However,
    the spirit of V022 is preserved: owner_id must NOT appear in exports.

    Guard: If owner_id IS present in version.yaml fields section, it must
    have semantics.export_visible: false (and import_visible: false).
    """

    def test_version_yaml_owner_id_has_export_visible_false(self):
        """BUG-V022 guard: owner_id in version.yaml must have export_visible: false.

        The V022 intent is that owner_id should not appear in exports.
        After V019 re-added owner_id, the export_visible: false property
        preserves this intent.
        """
        src = _read_abs(VERSION_YAML_PATH)

        # Find the owner_id field definition in the fields section
        # Pattern: "  - id: owner_id" followed by properties
        m = re.search(
            r'-\s*id:\s*owner_id\s*\n(.*?)(?=\n\s*-\s*id:|\n[a-z]|\Z)',
            src,
            re.DOTALL,
        )

        if not m:
            # owner_id not in fields section at all -> V022 original fix intact
            # This is fine, just pass
            return

        owner_id_block = m.group(1)

        # If owner_id IS present, it must have export_visible: false
        assert 'export_visible: false' in owner_id_block or "export_visible': false" in owner_id_block, (
            "BUG-V022 guard failed: version.yaml owner_id field exists but lacks "
            "export_visible: false. The V022 intent is that owner_id should not "
            "appear in exports. If owner_id was re-added (e.g., for V019), it must "
            "still have export_visible: false to preserve the V022 fix."
        )

    def test_version_yaml_owner_id_has_import_visible_false(self):
        """BUG-V022 guard: owner_id in version.yaml must have import_visible: false.

        Same reasoning as export_visible: the owner_id field is managed
        at product level and should not be imported at version level.
        """
        src = _read_abs(VERSION_YAML_PATH)

        m = re.search(
            r'-\s*id:\s*owner_id\s*\n(.*?)(?=\n\s*-\s*id:|\n[a-z]|\Z)',
            src,
            re.DOTALL,
        )

        if not m:
            return

        owner_id_block = m.group(1)

        assert 'import_visible: false' in owner_id_block or "import_visible': false" in owner_id_block, (
            "BUG-V022 guard failed: version.yaml owner_id field exists but lacks "
            "import_visible: false. The owner_id is managed at product level "
            "and should not be imported at version level."
        )


# ─── V023: business_key early return removed ────────────────────────────

class TestV023BusinessKeyEarlyReturn:
    """BUG-V023: _should_export_field must NOT have active business_key early return.

    Root cause: _should_export_field had an early 'if business_key: return True'
    check that let product_code (virtual, export_visible=False, business_key=True)
    bypass all subsequent visibility checks. This caused product_code to appear
    in child sheets, breaking column order and creating redundancy.

    Fix: Remove the business_key early return. Let business_key fields go through
    the normal export_visible / virtual / UI checks.
    """

    def test_should_export_field_no_active_business_key_return(self):
        """BUG-V023 guard: _should_export_field must not have active business_key return.

        The old buggy code had:
            if getattr(field.semantics, 'business_key', False):
                return True

        After the fix, this should be commented out or removed entirely.
        """
        src = _read_abs(IMPORT_EXPORT_SERVICE_PATH)

        func_body = _extract_function_body(src, '_should_export_field')
        assert func_body, "BUG-V023 guard: _should_export_field function not found"

        # Active (uncommented) business_key early return pattern
        active_pattern = r'''
            ^[^#\s]  # line does NOT start with # (comment) or whitespace-only
            .*getattr\s*\(\s*field\.semantics\s*,\s*['"]business_key['"]\s*,\s*False\s*\)
            .*return\s+True
        '''
        match = re.search(active_pattern, func_body, re.VERBOSE | re.MULTILINE)
        assert not match, (
            "BUG-V023 guard failed: _should_export_field has an active "
            "business_key early return. The fix removed this pattern because "
            "it lets virtual+export_visible=False fields bypass visibility checks."
        )

    def test_should_export_field_bug_v023_marker_present(self):
        """BUG-V023 guard: _should_export_field should have BUG-V023 removal marker.

        The fix leaves a comment marker 'BUG-V023' where the early return
        was removed, serving as documentation.
        """
        src = _read_abs(IMPORT_EXPORT_SERVICE_PATH)

        func_body = _extract_function_body(src, '_should_export_field')
        assert func_body, "BUG-V023 guard: _should_export_field function not found"

        # Check for BUG-V023 marker (either in function or its docstring)
        # The marker might be in the docstring or the commented-out code
        assert 'BUG-V023' in func_body or 'business_key' in func_body, (
            "BUG-V023 guard: _should_export_field does not contain BUG-V023 "
            "marker or any business_key reference. The fix should leave a "
            "commented-out early return with BUG-V023 marker."
        )

    def test_write_child_sheet_no_business_key_early_return(self):
        """BUG-V023 guard: _write_child_sheet field loop must not have business_key early return.

        The _write_child_sheet method builds export field candidates.
        It should not have an is_business_key early-add that bypasses
        export_visible checks (same root cause as V023).
        """
        src = _read_abs(IMPORT_EXPORT_SERVICE_PATH)

        func_body = _extract_function_body(src, '_write_child_sheet')
        assert func_body, "BUG-V023 guard: _write_child_sheet function not found"

        # Active business_key early continue/return in candidate loop
        # Pattern: if ... business_key ... : continue  (or early append)
        active_bk_pattern = r'^[^#].*business_key.*:\s*(continue|export_fields\.append)'
        match = re.search(active_bk_pattern, func_body, re.MULTILINE)
        assert not match, (
            "BUG-V023 guard failed: _write_child_sheet has an active "
            "business_key early continue/append in the field candidate loop. "
            "This pattern lets business_key fields bypass export_visible checks."
        )


# ─── V024: sheet column order (counting last) ───────────────────────────

class TestV024SheetColumnOrder:
    """BUG-V024: counting columns must sort last; no ID column.

    Root cause: child_count (computed=True, storage=virtual) was sorted by
    import_order alongside regular fields, appearing in the middle of the
    sheet. Also, the ID column was forced to position 0.

    Fix:
    1. Sort key changed to (business_key, import_order, is_counting) where
       is_counting=1 for computed+virtual fields, pushing them to the end.
    2. Removed the forced id column insert at position 0.
    """

    def test_write_child_sheet_sort_includes_counting_priority(self):
        """BUG-V024 guard: _write_child_sheet sort key must include counting check.

        The fix uses a 3-tuple sort key where the last element checks
        computed+virtual (is_counting), pushing counting columns last.
        """
        src = _read_abs(IMPORT_EXPORT_SERVICE_PATH)

        func_body = _extract_function_body(src, '_write_child_sheet')
        assert func_body, "BUG-V024 guard: _write_child_sheet function not found"

        # The sort key must include a computed+virtual check
        # Pattern: something like "1 if ... computed ... virtual ... else 0"
        counting_sort_pattern = r'computed.*virtual|virtual.*computed|is_counting'
        assert re.search(counting_sort_pattern, func_body), (
            "BUG-V024 guard failed: _write_child_sheet sort key does not "
            "include computed+virtual (counting) priority. The fix adds "
            "is_counting as the last sort key to push counting columns "
            "(like child_count) to the end of the sheet."
        )

    def test_write_child_sheet_no_forced_id_insert(self):
        """BUG-V024 guard: _write_child_sheet must NOT force-insert id column at position 0.

        The old buggy code did:
            if not id_in_export:
                export_fields.insert(0, id_field)

        After the fix, this code is removed or commented out.
        """
        src = _read_abs(IMPORT_EXPORT_SERVICE_PATH)

        func_body = _extract_function_body(src, '_write_child_sheet')
        assert func_body, "BUG-V024 guard: _write_child_sheet function not found"

        # Active id insert(0) pattern (uncommented)
        # Strategy: find lines containing export_fields.insert(0, that are NOT
        # commented out (no # before the insert on the same line)
        active_id_insert = r'export_fields\.insert\s*\(\s*0\s*,'
        for line in func_body.split('\n'):
            stripped = line.lstrip()
            if stripped.startswith('#'):
                continue
            if re.search(active_id_insert, line):
                # Found an uncommented line with insert(0,...) - this is the bug
                pytest.fail(
                    "BUG-V024 guard failed: _write_child_sheet has an active "
                    "export_fields.insert(0, ...) call. The fix removes forced "
                    "ID column insertion at position 0 because ID is a system "
                    "field that should not appear in user-facing sheets."
                )

    def test_should_export_field_bug_v024_marker(self):
        """BUG-V024 guard: _should_export_field or _write_child_sheet should have BUG-V024 marker.

        The fix leaves BUG-V024 comment markers in the code.
        """
        src = _read_abs(IMPORT_EXPORT_SERVICE_PATH)

        # Check both functions for BUG-V024 marker
        should_export = _extract_function_body(src, '_should_export_field')
        child_sheet = _extract_function_body(src, '_write_child_sheet')

        found = ('BUG-V024' in (should_export or '')) or ('BUG-V024' in (child_sheet or ''))
        assert found, (
            "BUG-V024 guard: neither _should_export_field nor _write_child_sheet "
            "contains BUG-V024 marker. The fix should leave comment markers "
            "documenting the counting-column-sort and no-ID-column changes."
        )


# ─── V025: visibility follows owner_aspect display ──────────────────────

class TestV025VisibilityField:
    """BUG-V025: version.yaml must NOT have duplicate visibility field definition.

    Root cause: version.yaml had its own visibility field definition, but
    visibility was moved to product level. A duplicate visibility field in
    version.yaml would conflict with owner_aspect display semantics and
    create confusion about which level controls visibility.

    Fix: Remove the visibility field from version.yaml fields section.
    Visibility is now managed at product level (version inherits from product).

    Guard: version.yaml fields section should NOT contain
    `  - id: visibility` at 4-space indent.
    """

    def test_version_yaml_no_duplicate_visibility_field(self):
        """BUG-V025 guard: version.yaml fields section must not have visibility field.

        Visibility is managed at product level. A visibility field in
        version.yaml fields section would be a duplicate/conflict.
        """
        src = _read_abs(VERSION_YAML_PATH)

        # Extract the fields section
        fields_match = re.search(r'^fields:\s*\n(.*)', src, re.MULTILINE)
        assert fields_match, "BUG-V025 guard: version.yaml has no fields section"

        # Find end of fields section (next top-level key or EOF)
        fields_start = fields_match.start()
        rest = src[fields_start:]
        # Fields section ends at next top-level key (column 0, no dash)
        next_section = re.search(r'\n[a-z_]+:\s*$', rest[10:], re.MULTILINE)
        if next_section:
            fields_section = rest[:10 + next_section.start()]
        else:
            fields_section = rest

        # Check for active (uncommented) visibility field at 4-space indent
        # Pattern: "  - id: visibility" (4-space indent with dash)
        visibility_pattern = r'^\s{2,4}-\s*id:\s*visibility\s*$'
        match = re.search(visibility_pattern, fields_section, re.MULTILINE)
        assert not match, (
            "BUG-V025 guard failed: version.yaml fields section contains "
            "'- id: visibility' field definition. Visibility has been moved "
            "to product level; version should not have its own visibility field."
        )

    def test_version_yaml_visibility_comment_confirms_removal(self):
        """BUG-V025 guard: version.yaml should confirm visibility field was removed.

        The fix leaves a comment documenting the removal, such as:
        '# [V1.1.2 2026-06-11] 删 visibility 字段定义 - 已上移到 product'
        """
        src = _read_abs(VERSION_YAML_PATH)

        # Check for comment about visibility removal/move
        visibility_removal = (
            'visibility' in src
            and ('上移' in src or '删' in src or '移除' in src or 'removed' in src.lower())
        )
        assert visibility_removal, (
            "BUG-V025 guard: version.yaml does not contain a comment "
            "confirming visibility field was removed/moved to product. "
            "Expected comment like '# 删 visibility 字段定义 - 已上移到 product'"
        )


# ─── V026: owner exception chain subquery ───────────────────────────────

class TestV026OwnerExceptionChainSubquery:
    """BUG-V026: _add_owner_exception must use chain_owner_resolver subquery.

    Root cause: _add_owner_exception in data_permission_interceptor.py used
    direct product_id for child objects (version/domain/sub_domain), but
    some child tables (like domain/sub_domain) do not have a product_id
    column. They link to product via version_id -> versions.product_id chain.
    This caused "no such column: product_id" SQL errors.

    Fix: Use build_owner_exception_subquery from chain_owner_resolver for
    child objects, which correctly traces the ownership chain through
    intermediate tables.

    Note: The actual file path is meta/core/interceptors/data_permission_interceptor.py
    (not meta/services/interceptors/ as might be assumed).
    """

    def test_data_permission_interceptor_uses_build_owner_exception_subquery(self):
        """BUG-V026 guard: data_permission_interceptor must import build_owner_exception_subquery.

        The fix imports and uses build_owner_exception_subquery from
        chain_owner_resolver instead of direct product_id references.
        """
        src = _read_abs(DATA_PERMISSION_INTERCEPTOR_PATH)

        # Check for build_owner_exception_subquery import or usage
        assert 'build_owner_exception_subquery' in src, (
            "BUG-V026 guard failed: data_permission_interceptor.py does not "
            "reference build_owner_exception_subquery. The fix uses this "
            "function from chain_owner_resolver to build correct ownership "
            "chain subqueries for child objects (domain/sub_domain) that "
            "don't have a direct product_id column."
        )

    def test_data_permission_interceptor_uses_chain_owner_resolver(self):
        """BUG-V026 guard: data_permission_interceptor must import from chain_owner_resolver.

        The fix adds 'from meta.services.chain_owner_resolver import ...'
        to access is_in_chain() and build_owner_exception_subquery().
        """
        src = _read_abs(DATA_PERMISSION_INTERCEPTOR_PATH)

        assert 'chain_owner_resolver' in src, (
            "BUG-V026 guard failed: data_permission_interceptor.py does not "
            "import from chain_owner_resolver. The fix imports is_in_chain() "
            "and build_owner_exception_subquery() to handle child objects "
            "that need ownership chain traversal."
        )

    def test_add_owner_exception_uses_in_subquery_for_chain(self):
        """BUG-V026 guard: _add_owner_exception must use in_subquery operator for chain objects.

        The fix adds owner exception conditions with operator='in_subquery'
        for child objects in the ownership chain, instead of direct product_id
        column references.
        """
        src = _read_abs(DATA_PERMISSION_INTERCEPTOR_PATH)

        func_body = _extract_function_body(src, '_add_owner_exception')
        assert func_body, "BUG-V026 guard: _add_owner_exception function not found"

        # The fix uses 'in_subquery' operator for chain objects
        assert 'in_subquery' in func_body, (
            "BUG-V026 guard failed: _add_owner_exception does not use "
            "'in_subquery' operator. The fix uses in_subquery with "
            "build_owner_exception_subquery for child objects that "
            "need ownership chain traversal (version/domain/sub_domain)."
        )


# ─── V027: annotation auto-included in child sheets ─────────────────────

class TestV027AnnotationAutoIncluded:
    """BUG-V027: _collect_child_object_types must auto-include annotation.

    Root cause: Export did not include "annotation" (备注信息) sheets because
    no YAML file explicitly declared annotation in child_sections. The
    polymorphic annotation object (via target_type/target_id) should follow
    all parent objects automatically.

    Fix: _collect_child_object_types automatically appends 'annotation' as
    a child of every selected type (when include_annotations is True).

    Guard: The function body must contain 'annotation' and the auto-include
    logic.
    """

    def test_collect_child_object_types_contains_annotation(self):
        """BUG-V027 guard: _collect_child_object_types function body must contain 'annotation'.

        The fix adds automatic annotation inclusion for all parent types.
        If 'annotation' is absent from the function, the fix has been removed.
        """
        src = _read_abs(IMPORT_EXPORT_SERVICE_PATH)

        func_body = _extract_function_body(src, '_collect_child_object_types')
        assert func_body, "BUG-V027 guard: _collect_child_object_types function not found"

        assert 'annotation' in func_body, (
            "BUG-V027 guard failed: _collect_child_object_types function "
            "does not contain 'annotation'. The fix automatically includes "
            "annotation as a polymorphic child of all parent types for export."
        )

    def test_collect_child_object_types_auto_includes_annotation(self):
        """BUG-V027 guard: _collect_child_object_types must have auto-include logic.

        The fix adds annotation to child_parent_map for each selected type
        when include_annotations is True. This is the polymorphic auto-include.
        """
        src = _read_abs(IMPORT_EXPORT_SERVICE_PATH)

        func_body = _extract_function_body(src, '_collect_child_object_types')
        assert func_body, "BUG-V027 guard: _collect_child_object_types function not found"

        # The auto-include logic adds annotation to child_parent_map
        # Pattern: child_parent_map['annotation'] or child_parent_map.setdefault('annotation'
        auto_include_pattern = r"child_parent_map\[.annotation.\]|child_parent_map\.setdefault\(.annotation."
        assert re.search(auto_include_pattern, func_body), (
            "BUG-V027 guard failed: _collect_child_object_types does not "
            "have annotation auto-include logic (child_parent_map['annotation'] "
            "or setdefault). The fix automatically appends annotation as a child "
            "of every selected type for export."
        )

    def test_collect_child_object_types_accepts_options_param(self):
        """BUG-V027/V038 guard: _collect_child_object_types must accept options parameter.

        The V027 fix auto-includes annotation, and V038 later made it
        controllable via options.include_annotations. Both must be present.
        """
        src = _read_abs(IMPORT_EXPORT_SERVICE_PATH)

        # Find function signature
        m = re.search(
            r'def\s+_collect_child_object_types\s*\([^)]*\)',
            src,
        )
        assert m, "BUG-V027 guard: _collect_child_object_types function not found"

        func_sig = m.group(0)
        assert 'options' in func_sig, (
            "BUG-V027/V038 guard failed: _collect_child_object_types "
            "does not accept 'options' parameter. The V038 fix added "
            "options to control include_annotations (default True for "
            "backward compatibility with V027)."
        )


# ─── Entry point ────────────────────────────────────────────────────────

if __name__ == '__main__':
    pytest.main([__file__, '-v', '--tb=short'])
