#!/usr/bin/env python
# -*- coding: utf-8 -*-
#
# Copyright 2021-2022 University of Illinois
#
# This file has been modified from the original ElasticNotebook.
# Original: https://github.com/illinoisdata/ElasticNotebook
class CellExecution:
    """
    A cell execution (object) corresponds to a cell execution (action, i.e. press play) in the notebook session.
    """

    def __init__(
        self,
        cell_num: int,
        cell: str,
        cell_runtime: float,
        start_time: float,
        src_vss: set,
        dst_vss: set,
    ):
        """
        Create an operation event from cell execution metrics.
        Args:
            cell_num (int): The nth cell execution of the current session.
            cell (str): The raw cell source code.
            cell_runtime (float): Cell runtime.
            start_time (time): Time of start of cell execution. Note that this is different from when the cell was
                queued.
            src_vss (List[VariableSnapshot]): Nodeset containing input VSs of the cell execution.
            dst_vss (List[VariableSnapshot]): Nodeset containing output VSs of the cell execution.
        """
        self.cell_num = cell_num
        self.cell = cell
        self.cell_runtime = cell_runtime
        self.start_time = start_time

        self.src_vss = src_vss
        self.dst_vss = dst_vss
