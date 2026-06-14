# This file has been modified from the original ElasticNotebook.
# Original: https://github.com/illinoisdata/ElasticNotebook

from typing import Dict

from elastic_notebook.core.graph.graph import DependencyGraph


class CheckpointFile:
    """
    Metadata container for a notebook checkpoint (serialized with dill).
    """

    def __init__(self):
        # Dependency graph representation of the notebook.
        self.dependency_graph = None

        # Migrated variables.
        self.variables = None

        # Active VSs corresponding to migrated variables.
        self.vss_to_migrate = None

        # Variables to recompute post-migration.
        self.vss_to_recompute = None

        # CEs to recompute to restore non-migrated variables (vss_to_recompute).
        self.ces_to_recompute = None

        # CEs to recompute a given CE. For fault tolerance if certain VSs fail
        # to deserialize.
        self.recomputation_ces = None

        # List of objects packed in the pickle file.
        self.serialization_order = None

        # User-declared functions in the session.
        self.udfs = None

    def with_dependency_graph(self, graph: DependencyGraph):
        self.dependency_graph = graph
        return self

    def get_dependency_graph(self):
        return self.dependency_graph

    def with_variables(self, variables: Dict):
        self.variables = variables
        return self

    def get_variables(self):
        return self.variables

    def with_vss_to_migrate(self, vss_to_migrate: set):
        self.vss_to_migrate = vss_to_migrate
        return self

    def get_vss_to_migrate(self):
        return self.vss_to_migrate

    def with_vss_to_recompute(self, vss_to_recompute: set):
        self.vss_to_recompute = vss_to_recompute
        return self

    def get_vss_to_recompute(self):
        return self.vss_to_recompute

    def with_ces_to_recompute(self, ces_to_recompute: set):
        self.ces_to_recompute = ces_to_recompute
        return self

    def get_ces_to_recompute(self):
        return self.ces_to_recompute

    def with_recomputation_ces(self, recomputation_ces: dict):
        self.recomputation_ces = recomputation_ces
        return self

    def get_recomputation_ces(self):
        return self.recomputation_ces

    def with_serialization_order(self, serialization_order: list):
        self.serialization_order = serialization_order
        return self

    def get_serialization_order(self):
        return self.serialization_order

    def with_udfs(self, udfs: set):
        self.udfs = udfs
        return self

    def get_udfs(self):
        return self.udfs
