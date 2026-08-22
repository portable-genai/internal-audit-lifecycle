"""The managed audit edge refuses to start while sibling payload mappings are placeholders."""

import pytest

from internal_audit_lifecycle.managed_readiness import (
    INCOMPLETE_MANAGED_OPERATIONS,
    assert_managed_profile_ready,
)


def test_offline_and_exit_profiles_remain_available() -> None:
    assert_managed_profile_ready("local")
    assert_managed_profile_ready("onprem")


def test_managed_profile_refuses_while_operations_are_placeholders() -> None:
    assert INCOMPLETE_MANAGED_OPERATIONS
    with pytest.raises(RuntimeError, match="not production ready"):
        assert_managed_profile_ready("gcp")
