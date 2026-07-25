from evals._logic_repair_review_bundle import review_bundle_hash


def test_review_bundle_hash_binds_every_case_report(tmp_path) -> None:
    (tmp_path / "cases" / "one").mkdir(parents=True)
    (tmp_path / "shadow_report.json").write_text("summary", encoding="utf-8")
    report = tmp_path / "cases" / "one" / "review_report.json"
    report.write_text("first", encoding="utf-8")

    before = review_bundle_hash(tmp_path)
    report.write_text("second", encoding="utf-8")

    assert review_bundle_hash(tmp_path) != before
