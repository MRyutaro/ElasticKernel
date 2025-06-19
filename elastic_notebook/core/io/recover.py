#!/usr/bin/env python
# -*- coding: utf-8 -*-
#
# Copyright 2021-2022 University of Illinois

import _pickle
import dill

from elastic_notebook.core.graph.graph import DependencyGraph


def resume(filename):
    """
    Resumes the notebook from the checkpoint file.
    Args:
        filename (str): location of the checkpoint file.
    Returns:
        tuple: (dependency_graph, fingerprint_dict, udfs, recomputation_ces, overlapping_vss)
    """
    try:
        with open(filename, "rb") as output_file:
            try:
                # 新しい形式で保存されたデータを読み込む
                graph, user_ns, udfs, metadata = dill.load(output_file)

                # fingerprint_dictを再構築
                fingerprint_dict = {}
                for var_name in user_ns:
                    if var_name in graph.variable_snapshots:
                        fingerprint_dict[var_name] = (
                            None,
                            set(),
                            None,
                        )  # 簡易的な指紋情報

                # metadataから情報を取得
                recomputation_ces = metadata.get("recomputation_ces", {})
                overlapping_vss = metadata.get("overlapping_vss", [])

                return graph, fingerprint_dict, udfs, recomputation_ces, overlapping_vss

            except _pickle.UnpicklingError:
                return DependencyGraph(), {}, set(), {}, []
            except EOFError:
                return DependencyGraph(), {}, set(), {}, []

    except Exception:
        return DependencyGraph(), {}, set(), {}, []
