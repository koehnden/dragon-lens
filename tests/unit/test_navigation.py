from ui.navigation import local_pages, public_pages


def test_public_demo_navigation_only_shows_dashboard() -> None:
    assert public_pages() == ["Dashboard"]


def test_local_navigation_keeps_full_app() -> None:
    assert local_pages() == ["Dashboard", "New Run", "Run History", "Settings"]
