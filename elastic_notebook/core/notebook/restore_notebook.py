import time
from logging import Logger

from ipykernel.zmqshell import ZMQInteractiveShell
from IPython.utils.capture import capture_output

from elastic_notebook.core.graph.graph import DependencyGraph


def restore_notebook(
    graph: DependencyGraph,
    shell: ZMQInteractiveShell,
    variables: dict,
    ces_to_recompute: set,
    logger: Logger,
):
    """
    Restores the notebook. Declares variables back into the kernel and recomputes the CEs to restore non-migrated
    variables.
    Args:
        graph (DependencyGraph): dependency graph representation of the notebook.
        shell (ZMQInteractiveShell): interactive Jupyter shell storing the state of the current session.
        variables (Dict): Mapping from OEs to lists of variables defined in those OEs.
        oes_to_recompute (set): OEs to recompute to restore non-migrated variables.
        logger (logging.Logger): Logger to write to.
    """

    # Recompute OEs following the order they were executed in.
    recompute_start = time.time()
    for ce in graph.cell_executions:
        if ce in ces_to_recompute:
            # Rerun cell code; suppress stdout when rerunning.
            cell_capture = capture_output(stdout=True, stderr=True, display=True)
            try:
                with cell_capture:
                    # TODO: ここを変えるとどうなるのか試す
                    # get_ipython().run_cell(ce.cell)
                    shell.run_cell(ce.cell)
            except Exception as e:
                raise e

        # Define output variables in the CE.
        for pair in variables[ce.cell_num]:
            shell.user_ns[pair[0].name] = pair[1]

    recompute_end = time.time()

    logger.debug(f"Recompute Time: {recompute_end - recompute_start}")
    logger.debug(f"{shell.user_ns=}")
