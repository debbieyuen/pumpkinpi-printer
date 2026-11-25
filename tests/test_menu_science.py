from pumpkinpi import menu_science as ms


def test_keeps_only_verified_searched_links():
    facts = [
        {"topic": "Tree nut labels", "fact": "FDA requires the nut type to be named.", "source": "FDA",
         "url": "https://www.fda.gov/food/allergens"},
        {"topic": "Blog", "fact": "x", "source": "Blog", "url": "https://someblog.com/a"},
        {"topic": "Not searched", "fact": "x", "source": "CDC", "url": "https://www.cdc.gov/made-up"},
    ]
    results = [{"url": "https://www.fda.gov/food/allergens/", "title": "Food Allergies | FDA"}]
    out = ms.clean(facts, results)["facts"]
    assert [f["topic"] for f in out] == ["Tree nut labels"]
    assert out[0]["title"] == "Food Allergies | FDA"


def test_research_uses_high_effort_and_verified_domains(monkeypatch):
    seen = {}

    def fake(client, **k):
        seen.update(k)
        return '{"facts": []}', []
    monkeypatch.setattr(ms.pplx, "agent", fake)
    ms.research(None, {"menu": [{"name": "Hot pot", "products": [{"item": "Kikkoman Ponzu"}]}]},
                [{"name": "Sam", "avoid": ["fish"]}, {"name": "Dad", "limit": ["sugar"]}])
    assert seen["effort"] == "high"
    assert "cdc.gov" in seen["domains"] and "fda.gov" in seen["domains"] and "pubmed.ncbi.nlm.nih.gov" in seen["domains"]
    assert "Kikkoman Ponzu" in seen["input"] and "sugar" in seen["input"]
