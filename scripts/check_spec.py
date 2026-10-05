"""StrictDocのモデル/APIを使って仕様ポリシーを検査するCLI。"""

from __future__ import annotations

import argparse
import io
import sys
from contextlib import redirect_stdout
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Any

from strictdoc.api import (
    Parallelizer,
    ProjectConfigLoader,
    SDocDocumentIterator,
    SDocNode,
    TraceabilityIndexBuilder,
)

ROLE_TAGS = frozenset({"FEATURE", "BEHAVIOR", "SCENARIO"})
TEST_SOURCE_ROOT = "tests/"
PRODUCTION_SOURCE_ROOT = "src/"


@dataclass(frozen=True)
class TestFunction:
    path: str
    name: str


@dataclass
class CheckResult:
    feature_count: int
    behavior_count: int
    scenario_count: int
    implemented_behavior_count: int
    tested_scenario_count: int
    passing_scenario_count: int | None
    errors: list[str]

    @property
    def passed(self) -> bool:
        return not self.errors


def _load_index(project_root: Path) -> Any:
    config = ProjectConfigLoader.load_from_path_or_get_default(
        path_to_config=str(project_root)
    )
    config.input_paths = [str(project_root)]
    config.validate_and_finalize()

    parallelizer = Parallelizer.create(parallelize=False)
    try:
        # The API builder emits progress messages to stdout. Keep the policy
        # check output concise without hiding parser exceptions.
        with redirect_stdout(io.StringIO()):
            return TraceabilityIndexBuilder.create(
                project_config=config,
                parallelizer=parallelizer,
            )
    finally:
        parallelizer.shutdown()


def _requirements(index: Any) -> list[SDocNode]:
    requirements: list[SDocNode] = []
    for document in index.document_tree.document_list:
        for node, _context in SDocDocumentIterator(document).all_content():
            if isinstance(node, SDocNode) and node.node_type == "REQUIREMENT":
                requirements.append(node)
    return requirements


def _explicit_parent_nodes(node: SDocNode, index: Any) -> list[SDocNode]:
    """Resolve only explicitly written Parent relations (not inverse Child links)."""
    parent_uids = [
        uid
        for relation_type, uid, _role in node.get_requirement_reference_uids()
        if relation_type == "Parent"
    ]
    return [
        parent
        for uid in parent_uids
        if isinstance((parent := index.get_node_by_uid(uid)), SDocNode)
    ]


def _node_uid(node: SDocNode) -> str:
    return node.reserved_uid or "<missing UID>"


def _node_tags(node: SDocNode) -> set[str]:
    return set(node.reserved_tags or [])


def _is_role(node: SDocNode, role: str) -> bool:
    return node.node_type == "REQUIREMENT" and role in _node_tags(node)


def _normalize_source_path(path: str) -> str:
    return PurePosixPath(path.replace("\\", "/")).as_posix()


def _function_names_for_marker(index: Any, path: str, marker: Any) -> list[str]:
    scope = getattr(getattr(marker, "scope", None), "value", None)
    if scope != "function":
        return []

    source_info = index.get_coverage_info_weak(path)
    if source_info is None:
        return []

    begin = getattr(marker, "ng_range_line_begin", None)
    end = getattr(marker, "ng_range_line_end", None)
    functions = source_info.functions
    exact_matches = [
        function
        for function in functions
        if function.line_begin == begin and function.line_end == end
    ]
    if exact_matches:
        return [function.display_name for function in exact_matches]

    # Parsers may report a slightly wider marker range. Accept a function only
    # when it unambiguously contains that range.
    containing_matches = [
        function
        for function in functions
        if begin is not None
        and end is not None
        and function.line_begin <= begin
        and end <= function.line_end
    ]
    if len(containing_matches) == 1:
        return [containing_matches[0].display_name]
    return []


def _pytest_functions_for_requirement(node: SDocNode, index: Any) -> set[TestFunction]:
    test_functions: set[TestFunction] = set()
    if not node.reserved_uid:
        return test_functions

    for path, markers in index.get_requirement_file_links(node):
        normalized_path = _normalize_source_path(path)
        if not normalized_path.startswith(TEST_SOURCE_ROOT):
            continue
        for marker in markers:
            for function_name in _function_names_for_marker(
                index, normalized_path, marker
            ):
                # Pytest collects functions/methods whose final name component
                # begins with `test_`.
                if function_name.rsplit(".", 1)[-1].startswith("test_"):
                    test_functions.add(TestFunction(normalized_path, function_name))
    return test_functions


def _production_links(node: SDocNode, index: Any) -> bool:
    if not node.reserved_uid:
        return False
    return any(
        _normalize_source_path(path).startswith(PRODUCTION_SOURCE_ROOT)
        for path, _markers in index.get_requirement_file_links(node)
    )


def _field_map(node: SDocNode) -> dict[str, str]:
    return {
        field.field_name: field.get_text_value()
        for field in node.enumerate_fields()
    }


def _junit_results(index: Any) -> tuple[bool, dict[TestFunction, list[str]]]:
    """Read imported JUnit Test Result nodes; missing reports remain unavailable."""
    results: dict[TestFunction, list[str]] = {}
    found_result_node = False

    for document in index.document_tree.document_list:
        for node, _context in SDocDocumentIterator(document).all_content():
            if not isinstance(node, SDocNode) or node.node_type != "TEST_RESULT":
                continue
            found_result_node = True
            fields = _field_map(node)
            path = fields.get("TEST_PATH")
            function = fields.get("TEST_FUNCTION")
            status = fields.get("STATUS", "UNKNOWN").upper()
            if path and function:
                key = TestFunction(_normalize_source_path(path), function)
                results.setdefault(key, []).append(status)

    return found_result_node, results


def _percentage(numerator: int, denominator: int) -> str:
    if denominator == 0:
        return "n/a"
    return f"{numerator / denominator * 100:.1f}%"


def check_project(project_root: Path) -> CheckResult:
    project_root = project_root.resolve()
    index = _load_index(project_root)
    requirements = _requirements(index)
    errors: list[str] = []

    tagged: dict[str, list[SDocNode]] = {role: [] for role in ROLE_TAGS}
    seen_uids: dict[str, SDocNode] = {}
    for node in requirements:
        uid = node.reserved_uid
        title = node.reserved_title or "(untitled)"
        tags = _node_tags(node)
        roles = tags & ROLE_TAGS

        if not uid:
            errors.append(f"<missing UID>: Requirement has no UID: {title!r}.")
        elif uid in seen_uids and seen_uids[uid] is not node:
            errors.append(f"{uid}: Duplicate Requirement UID.")
        else:
            seen_uids[uid] = node

        if len(roles) != 1:
            display_uid = uid or "<missing UID>"
            errors.append(
                f"{display_uid}: Requirement must have exactly one of the tags "
                "FEATURE, BEHAVIOR, or SCENARIO."
            )
            continue
        tagged[next(iter(roles))].append(node)

    for role, nodes in tagged.items():
        if not nodes:
            errors.append(f"No Requirement tagged {role} was found.")

    features = tagged["FEATURE"]
    behaviors = tagged["BEHAVIOR"]
    scenarios = tagged["SCENARIO"]

    scenario_test_functions: dict[str, set[TestFunction]] = {}
    tested_scenario_uids: set[str] = set()
    for scenario in scenarios:
        uid = _node_uid(scenario)
        title = scenario.reserved_title or "(untitled)"
        test_functions = _pytest_functions_for_requirement(scenario, index)
        scenario_test_functions[uid] = test_functions
        if test_functions:
            tested_scenario_uids.add(uid)
        else:
            errors.append(
                f'{uid}: Scenario has no linked pytest test function: "{title}".'
            )

        parents = _explicit_parent_nodes(scenario, index)
        if len(parents) != 1 or not _is_role(parents[0], "BEHAVIOR"):
            parent_description = (
                ", ".join(
                    f"{_node_uid(parent)} ({', '.join(sorted(_node_tags(parent))) or 'untagged'})"
                    for parent in parents
                )
                or "none"
            )
            errors.append(
                f"{uid}: Scenario must have exactly one Parent Relation to a "
                f"BEHAVIOR Requirement (found {parent_description})."
            )

    implemented_behavior_uids: set[str] = set()
    scenarios_by_parent: dict[str, list[SDocNode]] = {}
    for scenario in scenarios:
        for parent in _explicit_parent_nodes(scenario, index):
            parent_uid = parent.reserved_uid
            if parent_uid:
                scenarios_by_parent.setdefault(parent_uid, []).append(scenario)

    for behavior in behaviors:
        uid = _node_uid(behavior)
        title = behavior.reserved_title or "(untitled)"
        if _production_links(behavior, index):
            implemented_behavior_uids.add(uid)
        else:
            errors.append(
                f'{uid}: Behavior has no linked production source under src/: "{title}".'
            )

        if not scenarios_by_parent.get(uid):
            errors.append(f"{uid}: Behavior has no child Scenario.")

        parents = _explicit_parent_nodes(behavior, index)
        if len(parents) != 1 or not _is_role(parents[0], "FEATURE"):
            parent_description = (
                ", ".join(
                    f"{_node_uid(parent)} ({', '.join(sorted(_node_tags(parent))) or 'untagged'})"
                    for parent in parents
                )
                or "none"
            )
            errors.append(
                f"{uid}: Behavior must have exactly one Parent Relation to a "
                f"FEATURE Requirement (found {parent_description})."
            )

    junit_available, junit_results = _junit_results(index)
    passing_scenario_uids: set[str] = set()
    if not junit_available:
        errors.append(
            "No imported JUnit TEST_RESULT nodes; run pytest with its JUnit "
            "report before the policy check."
        )
    else:
        for scenario in scenarios:
            uid = _node_uid(scenario)
            linked_functions = scenario_test_functions.get(uid, set())
            if not linked_functions:
                continue

            missing_results = [
                function
                for function in linked_functions
                if function not in junit_results
            ]
            nonpassing_statuses = {
                function: junit_results[function]
                for function in linked_functions
                if function in junit_results
                and any(status != "PASSED" for status in junit_results[function])
            }
            if missing_results:
                errors.append(
                    f"{uid}: Linked pytest function has no imported JUnit result: "
                    + ", ".join(
                        f"{function.path}::{function.name}"
                        for function in sorted(missing_results, key=lambda item: (item.path, item.name))
                    )
                    + "."
                )
            if nonpassing_statuses:
                details = ", ".join(
                    f"{function.path}::{function.name}={','.join(statuses)}"
                    for function, statuses in sorted(
                        nonpassing_statuses.items(),
                        key=lambda item: (item[0].path, item[0].name),
                    )
                )
                errors.append(f"{uid}: Linked pytest result did not PASS: {details}.")
            if not missing_results and not nonpassing_statuses:
                passing_scenario_uids.add(uid)

    return CheckResult(
        feature_count=len(features),
        behavior_count=len(behaviors),
        scenario_count=len(scenarios),
        implemented_behavior_count=len(implemented_behavior_uids),
        tested_scenario_count=len(tested_scenario_uids),
        passing_scenario_count=(
            len(passing_scenario_uids) if junit_available else None
        ),
        errors=errors,
    )


def render_result(result: CheckResult) -> str:
    lines = [
        "StrictDoc Policy Check",
        "",
        f"Features:   {result.feature_count}",
        f"Behaviors:  {result.behavior_count}",
        f"Scenarios:  {result.scenario_count}",
        "",
        "Behavior implementation coverage:",
        f"{result.implemented_behavior_count} / {result.behavior_count} "
        f"({_percentage(result.implemented_behavior_count, result.behavior_count)})",
        "",
        "Scenario test coverage:",
        f"{result.tested_scenario_count} / {result.scenario_count} "
        f"({_percentage(result.tested_scenario_count, result.scenario_count)})",
    ]
    if result.passing_scenario_count is None:
        lines.extend(["", "Scenario passing coverage:", "N/A (no imported JUnit results)"])
    else:
        lines.extend(
            [
                "",
                "Scenario passing coverage:",
                f"{result.passing_scenario_count} / {result.scenario_count} "
                f"({_percentage(result.passing_scenario_count, result.scenario_count)})",
            ]
        )

    if result.errors:
        lines.extend(["", "Errors:"])
        lines.extend(f"- {error}" for error in result.errors)
        lines.extend(["", "FAILED"])
    else:
        lines.extend(["", "PASSED"])
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--project-root",
        type=Path,
        default=Path(__file__).resolve().parents[1],
        help="StrictDoc project root (defaults to this repository).",
    )
    args = parser.parse_args(argv)

    try:
        result = check_project(args.project_root)
    except Exception as exc:  # Convert parser/config/API errors into a CI failure.
        print("StrictDoc Policy Check\n")
        print(f"ERROR: Could not load StrictDoc project: {exc}")
        print("\nFAILED")
        return 1

    print(render_result(result))
    return 0 if result.passed else 1


if __name__ == "__main__":
    sys.exit(main())
