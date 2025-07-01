from __future__ import print_function

import logging
import os
import time
import types
from datetime import datetime, timedelta, timezone
from logging.handlers import RotatingFileHandler
from os.path import dirname

from IPython.core.interactiveshell import InteractiveShell
from pympler import asizeof

from elastic_notebook.algorithm.baseline import MigrateAllBaseline, RecomputeAllBaseline
from elastic_notebook.algorithm.optimizer_exact import OptimizerExact
from elastic_notebook.algorithm.selector import OptimizerType
from elastic_notebook.core.common.profile_graph_size import profile_graph_size
from elastic_notebook.core.common.profile_migration_speed import profile_migration_speed
from elastic_notebook.core.graph.graph import DependencyGraph
from elastic_notebook.core.io.recover import resume
from elastic_notebook.core.mutation.fingerprint import (
    compare_fingerprint,
    construct_fingerprint,
)
from elastic_notebook.core.mutation.object_hash import UnserializableObj
from elastic_notebook.core.notebook.checkpoint import checkpoint
from elastic_notebook.core.notebook.find_input_vars import find_input_vars
from elastic_notebook.core.notebook.find_output_vars import find_created_deleted_vars
from elastic_notebook.core.notebook.restore_notebook import restore_notebook
from elastic_notebook.core.notebook.update_graph import update_graph


class JSTFormatter(logging.Formatter):
    """日本時間（JST）用のログフォーマッター"""

    def converter(self, timestamp):
        dt = datetime.fromtimestamp(timestamp)
        return dt.astimezone(timezone(timedelta(hours=9)))  # UTC+9

    def formatTime(self, record, datefmt=None):
        dt = self.converter(record.created)
        if datefmt:
            return dt.strftime(datefmt)
        return dt.strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]  # マイクロ秒を3桁まで表示


class ElasticNotebook:
    def __init__(self, shell: InteractiveShell, log_file_dir: str):
        self.shell = shell

        # Initialize the dependency graph for capturing notebook state.
        self.dependency_graph = DependencyGraph()

        # Migration properties.
        self.migration_speed_bps = 100000
        self.alpha = 1
        self.selector = OptimizerExact(migration_speed_bps=self.migration_speed_bps)

        # Dictionary of object fingerprints. For detecting modified references.
        self.fingerprint_dict = {}

        # Set of user-declared functions.
        self.udfs = set()

        # Flag if migration speed has been manually set. In this case, skip profiling of migration speed at checkpoint
        # time.
        self.manual_migration_speed = False

        # Strings for determining log filename. For experiments only.
        self.optimizer_name = ""
        self.notebook_name = ""

        # Total elapsed time spent inferring cell inputs and outputs.
        # For measuring overhead.
        self.total_recordevent_time = 0

        # Dict for recording overhead of profiling operations.
        self.profile_dict = {"idgraph": 0, "representation": 0}

        # マイグレーションと再計算の変数リスト
        self._vss_to_migrate = []
        self._vss_to_recompute = []

        # ロガーの設定
        self.log_file_path = os.path.join(log_file_dir, "ElasticNotebook.log")
        self.logger: logging.Logger
        self.__setup_logger()

    @property
    def vss_to_migrate(self):
        """マイグレーション対象の変数リストを取得"""
        return self._vss_to_migrate

    @property
    def vss_to_recompute(self):
        """再計算対象の変数リストを取得"""
        return self._vss_to_recompute

    def __setup_logger(self):
        # ロガーの設定
        self.logger = logging.getLogger("ElasticNotebookLogger")

        # 環境変数からログレベルを取得
        log_level_str = os.environ.get("ELASTIC_KERNEL_LOG_LEVEL", "INFO").upper()
        log_level = getattr(logging, log_level_str, logging.INFO)
        self.logger.setLevel(log_level)

        formatter = JSTFormatter(
            "[%(asctime)s %(name)s %(filename)s:%(lineno)d %(levelname)s] %(message)s",
            "%Y-%m-%d %H:%M:%S.%f",
        )

        # ローテーティングファイルハンドラー
        rotating_file_handler = RotatingFileHandler(
            self.log_file_path,
            maxBytes=5 * 1024 * 1024,
            backupCount=5,  # 5MBのログサイズでローテーション、5世代保存
        )
        rotating_file_handler.setLevel(log_level)
        rotating_file_handler.setFormatter(formatter)
        self.logger.addHandler(rotating_file_handler)

    def update_migration_lists(self, vss_to_migrate, vss_to_recompute):
        """マイグレーションと再計算の変数リストを更新"""
        self._vss_to_migrate = [vs.name for vs in vss_to_migrate]
        self._vss_to_recompute = [vs.name for vs in vss_to_recompute]

    def __str__(self):
        """文字列表現を定義"""
        return f"マイグレーション対象: {self.vss_to_migrate}\n再計算対象: {self.vss_to_recompute}"

    def record_event(self, cell, pre_execution_user_ns, start_time, cell_runtime):
        # Create id trees for output variables
        for var in self.dependency_graph.variable_snapshots.keys():
            if var not in self.fingerprint_dict and var in self.shell.user_ns:
                self.fingerprint_dict[var] = construct_fingerprint(
                    self.shell.user_ns[var], self.profile_dict
                )

        # Find input variables (variables potentially accessed) of the cell.
        input_variables, function_defs = find_input_vars(
            cell,
            set(self.dependency_graph.variable_snapshots.keys()),
            self.shell,
            self.udfs,
        )
        # Union of ID graphs of input variables. For detecting modifications to unserializable variables.
        input_variables_id_graph_union = set()
        for var in input_variables:
            if var in self.fingerprint_dict:
                input_variables_id_graph_union = input_variables_id_graph_union.union(
                    self.fingerprint_dict[var][1]
                )

        post_execution = set(self.shell.user_ns.keys())
        infer_start = time.time()

        # Find created and deleted variables by computing difference between namespace pre and post execution.
        created_variables, deleted_variables = find_created_deleted_vars(
            pre_execution_user_ns, post_execution
        )

        # Remove stored ID graphs for deleted variables.
        for var in deleted_variables:
            del self.fingerprint_dict[var]
            if var in self.udfs:
                self.udfs.remove(var)

        # Find modified variables by comparing ID graphs and object hashes.
        modified_variables = set()
        for k, v in self.fingerprint_dict.items():
            changed, overwritten = compare_fingerprint(
                self.fingerprint_dict[k],
                self.shell.user_ns[k],
                self.profile_dict,
                input_variables_id_graph_union,
            )
            if changed:
                modified_variables.add(k)

            # In the case of non-overwrite modification, the variable is additionally considered as accessed.
            if changed and not overwritten:
                input_variables.add(k)

            # A user defined function has been overwritten.
            elif overwritten and k in self.udfs:
                self.udfs.remove(k)

            # Select unserializable variables are assumed to be modified if accessed.
            if (
                not changed
                and not overwritten
                and isinstance(self.fingerprint_dict[k][2], UnserializableObj)
            ):
                if self.fingerprint_dict[k][1].intersection(
                    input_variables_id_graph_union
                ):
                    modified_variables.add(k)

        # Create ID graphs for output variables
        for var in created_variables:
            self.fingerprint_dict[var] = construct_fingerprint(
                self.shell.user_ns[var], self.profile_dict
            )

        # Record newly defined UDFs
        for udf in function_defs:
            if udf in self.shell.user_ns and isinstance(
                self.shell.user_ns[udf], types.FunctionType
            ):
                self.udfs.add(udf)

        # Update the dependency graph.
        update_graph(
            cell,
            cell_runtime,
            start_time,
            input_variables,
            created_variables.union(modified_variables),
            deleted_variables,
            self.dependency_graph,
        )

        # Update total recordevent time tally.
        infer_end = time.time()
        self.total_recordevent_time += infer_end - infer_start

    def set_migration_speed(self, migration_speed):
        try:
            if float(migration_speed) > 0:
                self.migration_speed_bps = float(migration_speed)
                self.manual_migration_speed = True
        except ValueError:
            pass

        self.selector.migration_speed_bps = self.migration_speed_bps

    def set_optimizer(self, optimizer):
        self.optimizer_name = optimizer

        if optimizer == OptimizerType.EXACT.value:
            self.selector = OptimizerExact(self.migration_speed_bps)
            self.alpha = 1
        elif optimizer == OptimizerType.EXACT_C.value:
            self.selector = OptimizerExact(self.migration_speed_bps)
            self.alpha = 20
        elif optimizer == OptimizerType.EXACT_R.value:
            self.selector = OptimizerExact(self.migration_speed_bps)
            self.alpha = 0.05
        elif optimizer == OptimizerType.MIGRATE_ALL.value:
            self.selector = MigrateAllBaseline(self.migration_speed_bps)
        elif optimizer == OptimizerType.RECOMPUTE_ALL.value:
            self.selector = RecomputeAllBaseline(self.migration_speed_bps)

    def set_notebook_name(self, name):
        self.notebook_name = name

    def checkpoint(self, filename):
        """チェックポイントを作成"""
        self.logger.debug(
            "comparison overhead - "
            + repr(
                asizeof.asizeof(self.dependency_graph)
                + asizeof.asizeof(self.fingerprint_dict)
            )
            + " bytes"
        )
        self.logger.debug(
            "notebook overhead - "
            + repr(asizeof.asizeof(self.shell.user_ns))
            + " bytes"
        )
        self.logger.debug(
            "Dependency graph storage overhead - "
            + repr(profile_graph_size(self.dependency_graph))
            + " bytes"
        )
        self.logger.debug(
            "Cell monitoring overhead - "
            + repr(self.total_recordevent_time)
            + " seconds"
        )

        # Profile the migration speed to filename.
        if not self.manual_migration_speed:
            self.migration_speed_bps = profile_migration_speed(
                dirname(filename), alpha=self.alpha
            )
            self.selector.migration_speed_bps = self.migration_speed_bps

        # Checkpoint the notebook.
        migrate_success, vss_to_migrate, vss_to_recompute = checkpoint(
            self.dependency_graph,
            self.shell,
            self.fingerprint_dict,
            self.selector,
            self.udfs,
            filename,
            self.profile_dict,
            self.logger,
            self.notebook_name,
            self.optimizer_name,
        )

        # マイグレーションが成功した場合のみ、マイグレーションと再計算の変数リストを更新
        if migrate_success:
            self.update_migration_lists(vss_to_migrate, vss_to_recompute)

        return migrate_success

    def load_checkpoint(self, filename):
        (
            self.dependency_graph,
            variables,
            oes_to_recompute,
            self.udfs,
        ) = resume(self.logger, filename)

        # Recompute missing VSs and redeclare variables into the kernel.
        restore_notebook(
            self.dependency_graph,
            self.shell,
            variables,
            oes_to_recompute,
            self.logger,
        )
