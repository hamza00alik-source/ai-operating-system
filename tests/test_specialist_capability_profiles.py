from opencompany_core.specialist_capabilities import derive_specialist_capabilities
from opencompany_core.specialist_roles import EXTRA_SPECIALIST_TITLES, SPECIALIST_TITLES
from opencompany_core.workforce import SPECIALIST_ROLE_SPECS


def test_all_500_specialists_have_distinct_domain_capability_profiles():
    assert len(SPECIALIST_ROLE_SPECS) == 500
    assert len({role.key for role in SPECIALIST_ROLE_SPECS}) == 500
    for department, primary_titles in SPECIALIST_TITLES.items():
        titles = (*primary_titles, *EXTRA_SPECIALIST_TITLES[department])
        assert len(titles) == 50
        profiles = [derive_specialist_capabilities(department, title) for title in titles]
        assert all(profile for profile in profiles)
        assert len(set(profiles)) == 50, department


def test_every_specialist_title_matches_at_least_one_curated_domain_method():
    for department, primary_titles in SPECIALIST_TITLES.items():
        titles = (*primary_titles, *EXTRA_SPECIALIST_TITLES[department])
        for title in titles:
            methods = derive_specialist_capabilities(department, title)
            assert methods, f"{department}: {title}"
