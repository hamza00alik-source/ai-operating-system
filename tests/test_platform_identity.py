from opencompany_core.platform import PLATFORM_ID, PLATFORM_NAME, PLATFORM_VERSION


def test_unified_platform_identity_is_canonical():
    assert PLATFORM_ID == "opencompany-aios"
    assert PLATFORM_NAME == "OpenCompany AIOS"
    assert PLATFORM_VERSION == "0.3.0"


def test_distribution_includes_only_the_unified_application_and_engine():
    import tomllib
    from pathlib import Path

    project = tomllib.loads((Path(__file__).parents[1] / "pyproject.toml").read_text())
    package_discovery = project["tool"]["setuptools"]["packages"]["find"]
    assert package_discovery["include"] == ["opencompany_app*", "opencompany_core*"]
    assert "ai_os*" in package_discovery["exclude"]
