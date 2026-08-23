from pathlib import Path


ROUTES = Path(__file__).parents[2] / "app" / "blueprints" / "practice" / "routes.py"


def test_practice_routes_delegate_language_and_pool_decisions_to_service():
    source = ROUTES.read_text(encoding="utf-8")

    assert "words_svc" not in source
    assert "get_current_language" not in source
    assert "get_eligible_items" not in source
    assert "get_start_state" in source
