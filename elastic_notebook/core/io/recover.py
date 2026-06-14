#!/usr/bin/env python
# -*- coding: utf-8 -*-
#
# Copyright 2021-2022 University of Illinois
#
# This file has been modified from the original ElasticNotebook.
# Original: https://github.com/illinoisdata/ElasticNotebook

import logging
import time
from collections import defaultdict
from pathlib import Path

import dill


def resume(filename: str = "./notebook.pickle"):
    """
    Reads the file at `filename` and unpacks the graph representation of the notebook, migrated variables, and
    instructions for recomputation.

    Returns the checkpoint metadata (a CheckpointFile) and the recovered variables.
    The metadata reflects any fault-tolerance updates to ces_to_recompute made when
    a variable group fails to unpickle (D-2).

    Args:
        filename (str): Location of the checkpoint file.
    """
    logger = logging.getLogger("ElasticNotebookLogger")

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

    load_end = time.time()

    logger.debug(f"load_time: {load_end - load_start}")
    logger.debug(f"{metadata=}")
    logger.debug(f"{variables=}")

    return metadata, variables
