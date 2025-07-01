from collections import defaultdict
from logging import Logger
from pathlib import Path

import dill

# from elastic_notebook.core.io.filesystem_adapter import FilesystemAdapter
from ipykernel.zmqshell import ZMQInteractiveShell

from elastic_notebook.core.common.checkpoint_file import CheckpointFile
from elastic_notebook.core.graph.graph import DependencyGraph


def migrate(
    graph: DependencyGraph,
    shell: ZMQInteractiveShell,
    vss_to_migrate: set,
    vss_to_recompute: set,
    ces_to_recompute: set,
    udfs,
    recomputation_ces,
    overlapping_vss,
    logger: Logger,
    filename: str = "./notebook.pickle",
):
    """
    Writes the graph representation of the notebook, migrated variables, and instructions for recomputation as the
    specified file.

    Args:
        graph (DependencyGraph): dependency graph representation of the notebook.
        shell (ZMQInteractiveShell): interactive Jupyter shell storing the state of the current session.
        vss_to_migrate (set): set of VSs to migrate.
        vss_to_recompute (set): set of VSs to recompute.
        ces_to_recompute (set): set of CEs to recompute post-migration.
        filename (str): the location to write the checkpoint to.
        udfs (set): set of user-declared functions.
        logger (logging.Logger): Logger to write to.
    """
    # Retrieve variables
    variables = defaultdict(list)
    for vs in vss_to_migrate:
        variables[vs.output_ce].append(vs)

    logger.debug("=" * 100)
    logger.debug(f"{vss_to_migrate=}")
    logger.debug(f"{vss_to_recompute=}")
    logger.debug(f"{ces_to_recompute=}")
    logger.debug(f"{recomputation_ces=}")
    logger.debug(f"{overlapping_vss=}")
    logger.debug(f"{udfs=}")

    # construct serialization order list.
    temp_dict = {}
    serialization_order = []
    for vs1, vs2 in overlapping_vss:
        if vs1 in temp_dict:
            temp_dict[vs1].add(vs2)
        elif vs2 in temp_dict:
            temp_dict[vs2].add(vs1)
        else:
            # create new entry
            new_set = {vs1, vs2}
            temp_dict[vs1] = new_set
            temp_dict[vs2] = new_set

    for vs in vss_to_migrate:
        if vs not in temp_dict:
            temp_dict[vs] = {vs}

    for v in temp_dict.values():
        serialization_order.append(list(v))

    metadata = (
        CheckpointFile()
        .with_dependency_graph(graph)
        .with_variables(variables)
        .with_vss_to_migrate(vss_to_migrate)
        .with_vss_to_recompute(vss_to_recompute)
        .with_ces_to_recompute(ces_to_recompute)
        .with_recomputation_ces(recomputation_ces)
        .with_serialization_order(serialization_order)
        .with_udfs(udfs)
    )

    logger.debug(f"{filename=}")

    with open(Path(filename), "wb") as output_file:
        dill.dump(metadata, output_file)
        for vs_list in serialization_order:
            obj_list = []
            for vs in vs_list:
                obj_list.append(shell.user_ns[vs.name])
            dill.dump(obj_list, output_file)
