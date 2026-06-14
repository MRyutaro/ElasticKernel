# This file has been modified from the original ElasticNotebook.
# Original: https://github.com/illinoisdata/ElasticNotebook


class Selector:
    """
    The `Selector` class provides interfaces to pick a subset of active VSs to migrate based on
        various heuristics and algorithms.
    """

    def __init__(self, migration_speed_bps=1):
        """
        Creates a Selector instance with a migration speed estimate. The dependency graph and active VS fields
        must be populated prior to calling select_vss.
        """
        self.dependency_graph = None
        self.active_vss = None
        self.overlapping_vss = None
        self.migration_speed_bps = migration_speed_bps

        # CEs required to recompute a variable last modified by a given CE.
        # Declared on the base so callers (e.g. checkpoint()) can rely on it.
        self.recomputation_ces: dict = {}

    def select_vss(self, notebook_name=None, optimizer_name=None) -> tuple:
        """
        Classes that inherit from the `Selector` class (such as `OptimizerExact`) should
        override `select_vss`.

        Returns:
            Tuple[set(VariableSnapshot), set(CellExecution)]: the VSs selected to migrate and
            the CEs selected to recompute.
        """
        raise NotImplementedError()
