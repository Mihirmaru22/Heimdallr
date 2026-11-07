from app.services.evaluation import load_keys


def test_set1_keys_preserve_39_rows_and_flag_uncertain_labels():
    keys = load_keys()
    expected = [keys[name] for name in ("windchill-us", "netsuite-uk", "veeva-india")]
    assert sum(len(key["must_include"]) for key in expected) == 39
    assert [len(key["must_include"]) for key in expected] == [12, 17, 10]
    assert sum(len(key["must_exclude"]) for key in expected) == 17
    provisional = [row for key in expected for row in key["must_include"]
                   if row.get("evidence_status") == "guess"]
    unresolved = [row for key in expected for row in key["must_include"]
                  if row.get("evidence_status") == "unresolved"]
    assert len(provisional) == 7
    assert len(unresolved) == 1
    assert "AUSA" not in {row["company"] for row in expected[0]["must_exclude"]}
