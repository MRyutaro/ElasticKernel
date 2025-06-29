import time
from collections import defaultdict
from pathlib import Path

import dill

from elastic_notebook.core.io.filesystem_adapter import FilesystemAdapter
from elastic_notebook.core.io.migrate import FILENAME


def resume(
    filename: str, write_log_location=None, notebook_name=None, optimizer_name=None
):
    """
    Reads the file at `filename` and unpacks the graph representation of the notebook, migrated variables, and
    instructions for recomputation.

    Args:
        filename (str): Location of the checkpoint file.

        write_log_location (str): location to write file read runtime to. For experimentation only.
        notebook_name (str): notebook name. For experimentation only.
        optimizer_name (str): optimizer name. For experimentation only.
    """

    # Reads from the default location if a file path isn't specified.
    adapter = FilesystemAdapter()

    load_start = time.time()
    if filename:
        read_path = filename
    else:
        read_path = FILENAME

    variables = defaultdict(list)

    with open(Path(read_path), "rb") as output_file:
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

    if filename:
        metadata = adapter.read_all(Path(filename))
    else:
        metadata = adapter.read_all(Path(FILENAME))
    load_end = time.time()

    if write_log_location:
        with open(
            write_log_location + "/load_checkpoint.txt",
            "a",
        ) as f:
            f.write("=" * 100 + "\n")
            f.write(f"load_time: {load_end - load_start}\n")
            f.write(f"{metadata=}\n")
            f.write(f"{variables=}\n")

    return (
        metadata.get_dependency_graph(),
        variables,
        metadata.get_vss_to_migrate(),
        metadata.get_vss_to_recompute(),
        metadata.get_ces_to_recompute(),
        metadata.get_udfs(),
    )
