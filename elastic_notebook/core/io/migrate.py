import logging
import time
from collections import defaultdict
from pathlib import Path

import dill
from ipykernel.zmqshell import ZMQInteractiveShell

from elastic_notebook.core.common.checkpoint_file import CheckpointFile
from elastic_notebook.core.graph.graph import DependencyGraph

logger = logging.getLogger("ElasticNotebookLogger")


def migrate(
    graph: DependencyGraph,
    shell: ZMQInteractiveShell,
    vss_to_migrate: set,
    vss_to_recompute: set,
    ces_to_recompute: set,
    udfs,
    recomputation_ces,
    overlapping_vss,
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

    # マイグレーション対象の変数数と合計サイズをログ出力
    total_vars = sum(len(vs_list) for vs_list in serialization_order)
    logger.info(f"Starting migration of {total_vars} variables to {filename}")

    # 各変数の名前とサイズ情報をデバッグ出力
    for vs_list in serialization_order:
        for vs in vs_list:
            var_name = vs.name
            if var_name in shell.user_ns:
                var_obj = shell.user_ns[var_name]
                var_type = type(var_obj).__name__
                if isinstance(var_obj, (list, tuple, set, dict)):
                    logger.debug(
                        f"  Variable '{var_name}' (type: {var_type}, length: {len(var_obj):,})"
                    )
                else:
                    logger.debug(f"  Variable '{var_name}' (type: {var_type})")

    with open(Path(filename), "wb") as output_file:
        # メタデータの保存
        logger.info("Saving metadata...")
        metadata_start = time.time()
        dill.dump(metadata, output_file)
        metadata_time = time.time() - metadata_start
        logger.info(f"Metadata saved in {metadata_time:.3f} seconds")

        # 変数の保存
        logger.info(f"Saving {len(serialization_order)} variable groups...")
        for i, vs_list in enumerate(serialization_order):
            group_start = time.time()
            obj_list = []

            # 変数グループの情報をログ出力
            var_names = [vs.name for vs in vs_list]
            logger.info(
                f"  Saving variable group {i+1}/{len(serialization_order)}: {var_names}"
            )

            for vs in vs_list:
                obj_list.append(shell.user_ns[vs.name])

            # 大きなリストの警告
            for obj in obj_list:
                if isinstance(obj, list) and len(obj) > 10000000:  # 1000万要素以上
                    logger.warning(
                        f"    WARNING: Very large list detected ({len(obj):,} elements). This may take a long time to serialize."
                    )
                    logger.warning(
                        f"    Consider using NumPy arrays or other more efficient data structures for large datasets."
                    )

            # dill.dumpの実行時間を計測
            dump_start = time.time()
            logger.debug(f"    Starting dill.dump for {len(obj_list)} objects...")

            # メモリ使用量をログ出力（可能な場合）
            try:
                import os

                import psutil

                process = psutil.Process(os.getpid())
                memory_info = process.memory_info()
                logger.info(
                    f"    Memory usage before dump: {memory_info.rss / 1024 / 1024:.1f} MB"
                )
            except ImportError:
                pass

            # タイムアウトの可能性を警告
            total_size = sum(
                len(obj) if isinstance(obj, (list, tuple, set, dict)) else 1
                for obj in obj_list
            )
            if total_size > 10000000:
                logger.warning(
                    f"    This operation may take several minutes. Total elements: {total_size:,}"
                )
                logger.warning(
                    f"    If the kernel becomes unresponsive, Jupyter may terminate it."
                )

            dill.dump(obj_list, output_file)
            dump_time = time.time() - dump_start

            group_time = time.time() - group_start
            logger.info(
                f"    Variable group {i+1} saved in {group_time:.3f} seconds (dump: {dump_time:.3f}s)"
            )

    logger.info("Migration completed successfully")
