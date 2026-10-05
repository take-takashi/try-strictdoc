from pathlib import Path

from scripts.check_spec import check_project


def _write_project(
    root: Path,
    *,
    scenario_parent: str = "BEH-1",
    behavior_parent: str = "FEAT-1",
    include_scenario: bool = True,
    implementation_relation: bool = True,
    test_relation: bool = True,
    junit_status: str | None = "passed",
) -> Path:
    (root / "docs").mkdir(parents=True)
    (root / "src").mkdir()
    (root / "tests").mkdir()
    (root / "reports").mkdir()

    scenario = """[REQUIREMENT]
UID: SCN-1
TAGS: SCENARIO
TITLE: Example scenario
STATEMENT: A scenario with a test.
RELATIONS:
- TYPE: Parent
  VALUE: {scenario_parent}
""".format(scenario_parent=scenario_parent) if include_scenario else ""
    (root / "docs/spec.sdoc").write_text(
        """[DOCUMENT]
TITLE: Policy fixture

[REQUIREMENT]
UID: FEAT-1
TAGS: FEATURE
TITLE: Example feature
STATEMENT: Feature statement.

[REQUIREMENT]
UID: BEH-1
TAGS: BEHAVIOR
TITLE: Example behavior
STATEMENT: Behavior statement.
RELATIONS:
- TYPE: Parent
  VALUE: {behavior_parent}

{scenario}""".format(behavior_parent=behavior_parent, scenario=scenario),
        encoding="utf-8",
    )

    implementation_marker = (
        "    @relation(BEH-1, scope=function)\n" if implementation_relation else ""
    )
    (root / "src/implementation.py").write_text(
        'def implement():\n    """\n'
        + implementation_marker
        + '    """\n    return True\n',
        encoding="utf-8",
    )
    test_marker = (
        "    @relation(SCN-1, scope=function)\n"
        if test_relation and include_scenario
        else ""
    )
    (root / "tests/test_spec.py").write_text(
        'def test_example_scenario():\n    """\n'
        + test_marker
        + '    """\n    assert True\n',
        encoding="utf-8",
    )

    (root / "strictdoc_config.py").write_text(
        """from strictdoc.api import ProjectConfig


def create_config():
    return ProjectConfig(
        project_title=\"Policy fixture\",
        project_features=[\"REQUIREMENT_TO_SOURCE_TRACEABILITY\"],
        source_root_path=\".\",
        include_doc_paths=[\"/docs/**\", \"/reports/**\"],
        include_source_paths=[\"/src/**\", \"/tests/**\"],
    )
""",
        encoding="utf-8",
    )

    if junit_status is not None:
        failure = (
            '<failure message="assertion failed" type="AssertionError">failed</failure>'
            if junit_status == "failed"
            else ""
        )
        skipped = '<skipped message="skipped" />' if junit_status == "skipped" else ""
        failures = "1" if junit_status == "failed" else "0"
        skips = "1" if junit_status == "skipped" else "0"
        (root / "reports/test_spec.pytest.junit.xml").write_text(
            """<?xml version=\"1.0\" encoding=\"utf-8\"?>
<testsuites name=\"pytest tests\">
  <testsuite name=\"pytest\" errors=\"0\" failures=\"{failures}\" skipped=\"{skips}\" tests=\"1\" time=\"0.001\">
    <testcase classname=\"tests.test_spec\" name=\"test_example_scenario\" time=\"0.001\">{failure}{skipped}</testcase>
  </testsuite>
</testsuites>
""".format(failures=failures, skips=skips, failure=failure, skipped=skipped),
            encoding="utf-8",
        )
    return root


def test_valid_scenario_policy_passes_and_reads_junit_status(tmp_path: Path) -> None:
    result = check_project(_write_project(tmp_path))

    assert result.passed, result.errors
    assert (result.feature_count, result.behavior_count, result.scenario_count) == (1, 1, 1)
    assert result.implemented_behavior_count == 1
    assert result.tested_scenario_count == 1
    assert result.passing_scenario_count == 1


def test_scenario_without_pytest_relation_fails(tmp_path: Path) -> None:
    result = check_project(_write_project(tmp_path, test_relation=False))

    assert not result.passed
    assert result.tested_scenario_count == 0
    assert any("Scenario has no linked pytest test function" in error for error in result.errors)


def test_behavior_without_production_relation_fails(tmp_path: Path) -> None:
    result = check_project(_write_project(tmp_path, implementation_relation=False))

    assert not result.passed
    assert result.implemented_behavior_count == 0
    assert any("Behavior has no linked production source" in error for error in result.errors)


def test_behavior_without_scenario_fails(tmp_path: Path) -> None:
    result = check_project(_write_project(tmp_path, include_scenario=False, junit_status=None))

    assert not result.passed
    assert any("BEH-1: Behavior has no child Scenario" in error for error in result.errors)


def test_scenario_with_feature_parent_fails(tmp_path: Path) -> None:
    result = check_project(_write_project(tmp_path, scenario_parent="FEAT-1"))

    assert not result.passed
    assert any("SCN-1: Scenario must have exactly one Parent Relation to a BEHAVIOR" in error for error in result.errors)


def test_behavior_with_scenario_parent_fails(tmp_path: Path) -> None:
    result = check_project(
        _write_project(
            tmp_path,
            behavior_parent="SCN-1",
            scenario_parent="FEAT-1",
        )
    )

    assert not result.passed
    assert any("BEH-1: Behavior must have exactly one Parent Relation to a FEATURE" in error for error in result.errors)


def test_missing_junit_report_fails_quality_gate(tmp_path: Path) -> None:
    result = check_project(_write_project(tmp_path, junit_status=None))

    assert not result.passed
    assert result.passing_scenario_count is None
    assert any("No imported JUnit TEST_RESULT nodes" in error for error in result.errors)


def test_scenario_with_failed_junit_result_fails_passing_coverage(tmp_path: Path) -> None:
    result = check_project(_write_project(tmp_path, junit_status="failed"))

    assert not result.passed
    assert result.tested_scenario_count == 1
    assert result.passing_scenario_count == 0
    assert any("Linked pytest result did not PASS" in error for error in result.errors)
