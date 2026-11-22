import pytest


@pytest.fixture(autouse=True)
def no_saved_menu(tmp_path, monkeypatch):
    """Tests use cards.example.json, never a menu someone made on this Pi."""
    from pumpkinpi import menu_plan
    monkeypatch.setattr(menu_plan, "MENU_FILE", tmp_path / "menu.json")
