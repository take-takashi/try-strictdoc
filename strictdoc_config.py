from strictdoc.core.project_config import ProjectConfig


def create_config() -> ProjectConfig:
    return ProjectConfig(
        project_title="Order Management SSOT PoC",
        project_features=[
            "TABLE_SCREEN",
            "TRACEABILITY_SCREEN",
            "DEEP_TRACEABILITY_SCREEN",
            "SEARCH",
            "TRACEABILITY_MATRIX_SCREEN",
            "TREE_MAP_SCREEN",
            "REQUIREMENT_TO_SOURCE_TRACEABILITY",
        ],
        source_root_path=".",
        include_doc_paths=["/docs/**", "/reports/**"],
        include_source_paths=["/src/**", "/tests/**"],
    )
