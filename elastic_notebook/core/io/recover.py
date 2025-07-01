import time
from collections import defaultdict
from logging import Logger
from pathlib import Path

import dill

from elastic_notebook.core.io.filesystem_adapter import FilesystemAdapter


def resume(logger: Logger, filename: str = "./notebook.pickle"):
    """
    Reads the file at `filename` and unpacks the graph representation of the notebook, migrated variables, and
    instructions for recomputation.

    Args:
        filename (str): Location of the checkpoint file.
        logger (logging.Logger): Logger to write to.
    """

    # Reads from the default location if a file path isn't specified.
    adapter = FilesystemAdapter()

    load_start = time.time()

    variables = defaultdict(list)

    with open(Path(filename), "rb") as output_file:
        metadata = dill.load(output_file)
        for vs_list in metadata.get_serialization_order():
            try:
                obj_list = dill.load(output_file)
                for i in range(len(vs_list)):
                    variables[vs_list[i].output_ce.cell_num].append(
                        (vs_list[i], obj_list[i])
                    )
            except Exception:
                # unpickling failed. Rerun cells to retrieve variable(s).
                for vs in vs_list:
                    if vs.output_ce in metadata.recomputation_ces:
                        metadata.ces_to_recompute = metadata.ces_to_recompute.union(
                            metadata.recomputation_ces[vs.output_ce]
                        )

    metadata = adapter.read_all(Path(filename))
    load_end = time.time()

    logger.debug(f"load_time: {load_end - load_start}")
    logger.debug(f"{metadata=}")
    logger.debug(f"{variables=}")

    return (
        metadata.get_dependency_graph(),
        variables,
        metadata.get_ces_to_recompute(),
        metadata.get_udfs(),
    )
