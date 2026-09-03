from scripts.check_core_portability import check


def test_new_core_surfaces_are_domain_neutral():
    assert check() == []
