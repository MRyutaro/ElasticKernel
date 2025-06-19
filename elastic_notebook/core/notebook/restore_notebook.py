import sys
import time
from io import StringIO

from ipykernel.zmqshell import ZMQInteractiveShell
from IPython import get_ipython

from elastic_notebook.core.graph.graph import DependencyGraph


def restore_notebook(
    graph: DependencyGraph,
    shell: ZMQInteractiveShell,
    variables: dict,
    ces_to_recompute: set,
    write_log_location=None,
    notebook_name=None,
    optimizer_name=None,
):
    """
    Restores the notebook. Declares variables back into the kernel and recomputes the CEs to restore non-migrated
    variables.
    Args:
        graph (DependencyGraph): dependency graph representation of the notebook.
        shell (ZMQInteractiveShell): interactive Jupyter shell storing the state of the current session.
        variables (Dict): Mapping from OEs to lists of variables defined in those OEs.
        oes_to_recompute (set): OEs to recompute to restore non-migrated variables.
        write_log_location (str): location to write component runtimes to. For experimentation only.
        notebook_name (str): notebook name. For experimentation only.
        optimizer_name (str): optimizer name. For experimentation only.
    """

    # Recompute OEs following the order they were executed in.
    recompute_start = time.time()
    for ce in graph.cell_executions:
        if ce in ces_to_recompute:
            # 出力を完全に抑制するための設定
            ipython = get_ipython()

            # 元のdisplay_pubを保存
            original_display_pub = ipython.display_pub

            # display_pubを一時的に無効化
            ipython.display_pub = None

            # stdoutとstderrをリダイレクト
            original_stdout = sys.stdout
            original_stderr = sys.stderr
            sys.stdout = StringIO()
            sys.stderr = StringIO()

            try:
                # セルを実行（出力は抑制される）
                cell_output = ipython.run_cell(ce.cell)
                cell_output.raise_error()
            except Exception as e:
                # エラーが発生した場合は元のstderrに出力
                sys.stderr = original_stderr
                raise e
            finally:
                # 元の設定を復元
                ipython.display_pub = original_display_pub
                sys.stdout = original_stdout
                sys.stderr = original_stderr

        # Define output variables in the CE.
        for pair in variables[ce.cell_num]:
            shell.user_ns[pair[0].name] = pair[1]

    recompute_end = time.time()

    if write_log_location:
        with open(
            write_log_location
            + "/output_"
            + notebook_name
            + "_"
            + optimizer_name
            + ".txt",
            "a",
        ) as f:
            f.write(
                "Recompute stage took - "
                + repr(recompute_end - recompute_start)
                + " seconds"
                + "\n"
            )
