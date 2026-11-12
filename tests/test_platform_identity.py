from opencompany_core.platform import PLATFORM_ID, PLATFORM_NAME, PLATFORM_VERSION


def test_unified_platform_identity_is_canonical():
    assert PLATFORM_ID == "opencompany-aios"
    assert PLATFORM_NAME == "OpenCompany AIOS"
    assert PLATFORM_VERSION == "0.3.0"
