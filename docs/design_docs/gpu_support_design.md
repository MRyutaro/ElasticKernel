# ElasticKernel GPU対応 設計書

本ドキュメントは、現在CPU上のPythonオブジェクトのみを対象としているElasticKernelのチェックポイント・復元機構を、GPU常駐状態（PyTorch CUDAテンソル、CuPy配列、GPU上のモデル・オプティマイザ状態など）に対応させるための設計指針を示す。**本ドキュメントは設計のみを扱い、実装は含まない。**

先行研究の調査結果は [gpu_support_prior_work.md](./gpu_support_prior_work.md) を参照。

作成日: 2026-06-12

---

## 目次

1. [背景と目的](#1-背景と目的)
2. [ユースケースと要件](#2-ユースケースと要件)
3. [現状のCPU-only仮定の整理](#3-現状のcpu-only仮定の整理)
4. [設計方針の決定](#4-設計方針の決定)
5. [詳細設計](#5-詳細設計)
6. [段階的実装計画](#6-段階的実装計画)
7. [未解決課題とリスク](#7-未解決課題とリスク)
8. [評価計画](#8-評価計画)

---

## 1. 背景と目的

### 1.1 背景

ElasticKernelは、セル間の変数依存関係を追跡し、コスト分析に基づいて変数を「マイグレート（dillでシリアライズ）」または「再計算（セル再実行）」に振り分けることで、ノートブック状態の保存・復元を最適化する。しかし現在の実装は変数がCPUメモリ上にあることを暗黙に仮定しており、GPU常駐オブジェクトに対しては以下の問題がある：

- **正しさの問題**: CUDAテンソルをdillでそのまま保存すると、復元先にGPUがない・デバイス番号が違う環境で `RuntimeError` を起こす（PyTorch issue [#16797](https://github.com/pytorch/pytorch/issues/16797)）。CuPy配列はカレントデバイス依存で復元される。CUDAコンテキスト・ストリーム・cuDNNハンドル等はそもそもシリアライズ不可能。
- **コストモデルの問題**: 変数サイズ計測（`sys.getsizeof`）はGPUバッファを見ないため数GBのテンソルを数KBと過小評価し、マイグレーション速度プロファイルはディスクI/Oのみを計測してGPU↔CPU転送（PCIe）コストを無視し、セル実行時間はCUDAの非同期実行のため過小計測される。結果として、オプティマイザのmigrate-vs-recompute判断がGPU変数に対して系統的に誤る。
- **変更検出の問題**: GPUテンソルのハッシュ計算はホストへの暗黙コピーを伴い、セル毎オーバーヘッドが激増する。in-place変更の検出も機能しない。

### 1.2 目的

1. GPU常駐変数を含むノートブックセッションを**正しく**チェックポイント・復元できるようにする（復元先のGPU有無・種類が異なる場合も含む）。
2. GPU↔CPU転送・GPU再計算のコストを**コストモデルに統合**し、GPU変数に対してもmigrate-vs-recomputeの最適判断を可能にする。
3. （副次目標）アイドル時にGPUメモリを解放し、復帰時に復元する「弾力的GPU利用」を可能にする。

### 1.3 研究上の位置づけ

先行研究調査（[gpu_support_prior_work.md](./gpu_support_prior_work.md) §1）の通り、ElasticNotebook (VLDB 2023) / Kishu (VLDB 2025) の系譜でGPU状態を一級市民として扱った研究は存在しない。具体的には以下が未解決であり、本設計の新規性となる：

- **GPU変数を含むmigrate-vs-recomputeコストモデル**（PCIe転送項、復元先デバイス可用性による再計算コストの分岐）
- **GPU変数の低オーバーヘッドな変更検出**（ホスト転送を伴わないフィンガープリンティング）
- **異種デバイス環境間でのノートブック状態の可搬性**（GPU→CPUオンリー環境への復元ポリシー）

---

## 2. ユースケースと要件

### 2.1 ユースケース

| # | ユースケース | 説明 | 優先度 |
|---|---|---|---|
| U1 | **同一GPUマシンでのセッション再開** | カーネル停止 → 同じマシンで再起動。GPU変数を元のデバイスに復元する。 | P0 |
| U2 | **GPUマシン → CPUオンリーマシンへの移行** | GPUインスタンスは高価なので、作業の区切りでCPUマシンに移って分析を続けたい。GPU変数はCPUに「降ろして」復元するか、再計算扱いにする。 | P1 |
| U3 | **CPUマシン → GPUマシンへの移行** | ElasticNotebook論文の動機そのもの。前処理をCPUマシンで行い、学習はGPUマシンで行う。 | P1 |
| U4 | **異種GPU間の移行**（A100→H100等） | デバイスタグの読み替えが必要。 | P2 |
| U5 | **アイドル時のGPU解放** | ノートブックを開いたままGPUメモリだけ解放し、他のジョブにGPUを明け渡す（Run:ai Memory Swapの変数選択版）。 | P2 |

### 2.2 機能要件

- **FR1**: PyTorch CUDAテンソル・`nn.Module`・オプティマイザ状態、CuPy配列を、復元先デバイスを問わず正しく保存・復元できること。
- **FR2**: GPU変数の真のサイズ（デバイスメモリ上のバイト数）をコストモデルが認識すること。
- **FR3**: マイグレーションコストにGPU→CPU転送（d2h）・CPU→GPU転送（h2d）の項が含まれること。
- **FR4**: 復元先にGPUがない場合、GPU必須セルの再計算コストを∞として扱い、該当変数の扱い（CPU配置 or 諦め）をポリシーで選べること。
- **FR5**: GPUを使うセルのRNG状態（`torch.cuda.get_rng_state` 等）を記録し、再計算の決定性を高めること。
- **FR6**: 対応外のGPUオブジェクト（TensorFlow/JAX等、当面のスコープ外）は、既存の「シリアライズ不能 → 再計算」フォールバックに安全に落ちること。

### 2.3 非機能要件

- **NFR1**: GPU非搭載環境での動作・性能に一切影響を与えないこと（torch/cupyを直接importしない既存方針を維持）。
- **NFR2**: セル実行ごとのオーバーヘッド増加を実行時間の5%以内に抑えること（特にフィンガープリンティングでのGPU→CPU暗黙コピーの排除）。
- **NFR3**: チェックポイントフォーマットの後方互換性を保つこと（GPUメタデータのないチェックポイントも読めること）。

---

## 3. 現状のCPU-only仮定の整理

コードベース調査の結果、GPU対応が必要な統合ポイントは以下の5層に整理できる。

### 3.1 シリアライゼーション層

| 箇所 | 現状 | 問題 |
|---|---|---|
| `elastic_notebook/core/io/migrate.py`（`dill.dump` による一括シリアライズ） | `shell.user_ns` から取り出したオブジェクトをそのままdillに渡す | CUDAテンソルはデバイスタグ付きで保存され、復元先にそのデバイスがないと失敗する。GPU→CPUコピー時間が計測されない |
| `elastic_notebook/core/io/recover.py:40-51`（unpickle失敗時の再計算フォールバック） | あらゆる例外を「シリアライズ失敗」として黙って再計算に回す | CUDAデバイス不在・GPU OOM・コンテキストエラーが区別されず、原因がログに残らない |
| `elastic_notebook/core/io/filesystem_adapter.py:16-24`（`read_all` の一括読み込み） | ファイル全体をホストメモリに展開してからデシリアライズ | 大規模GPU変数の復元時にホストRAMとGPUメモリの両方を二重消費する |

### 3.2 フィンガープリント・変更検出層

| 箇所 | 現状 | 問題 |
|---|---|---|
| `elastic_notebook/core/mutation/object_hash.py:125-136`（`is_torch_tensor`） | torchをimportせずにテンソルを判定するが、CPU/GPUを区別しない | GPUテンソルもCPUテンソルと同じパスに入る |
| `elastic_notebook/core/mutation/object_hash.py:258-262`（`np.ascontiguousarray(obj)` でxxhash） | テンソルをnumpy経由でハッシュ | CUDAテンソルでは**セル実行ごとにGPU→CPU全データコピー**が発生（または例外）。NFR2に抵触 |
| `elastic_notebook/core/mutation/object_hash.py:232-240`（モジュール名による`UncomparableObj`判定） | tensorflow/transformers等を比較不能として扱う | GPU起因かフレームワーク起因かの区別がなく、デバイス情報が捨てられる |
| `elastic_notebook/core/mutation/id_graph.py`（`id(obj)` ベースの参照追跡） | ホスト側Pythonオブジェクトのアドレスのみ記録 | 同一GPUバッファを共有するビュー（`tensor.view()` 等）の共有参照を検出できない |

### 3.3 コストモデル・オプティマイザ層

| 箇所 | 現状 | 問題 |
|---|---|---|
| `elastic_notebook/algorithm/optimizer_exact.py:88`（migration cost = `active_vs.size / migration_speed_bps`） | ディスクI/Oのみのコスト | d2h/h2d転送項がない |
| `elastic_notebook/algorithm/optimizer_exact.py:94`（recomputation cost = `ce.cell_runtime`） | wall clock時間 | CUDA非同期実行のため過小計測。復元先のGPU有無で再計算可能性が変わることを表現できない |
| `elastic_notebook/core/common/profile_variable_size.py:26`（`sys.getsizeof`） | Pythonオブジェクトサイズのみ | GPUテンソルは数KB扱い（実体は数GBでも）。**コストモデルが1000倍以上過小評価** |
| `elastic_notebook/core/common/profile_migration_speed.py:31-32, 63`（numpy配列のディスク書き込みで速度計測） | ディスク帯域のみ計測 | PCIe帯域が計測されない |

### 3.4 依存グラフ・メタデータ層

| 箇所 | 現状 | 問題 |
|---|---|---|
| `elastic_notebook/core/graph/variable_snapshot.py`（`VariableSnapshot`: name/version/size のみ） | デバイス情報なし | 変数がどのデバイスに常駐していたか復元時に分からない |
| `elastic_notebook/core/graph/cell_execution.py`（`CellExecution`: cell_runtime のみ） | GPU使用の有無を記録しない | 「このセルの再計算にはGPUが必要」を表現できない |
| `elastic_kernel/kernel.py` の `do_execute`（`time.time()` 差分で実行時間計測） | CUDA同期なし | GPU計算が終わる前に計測が終わる |

### 3.5 復元層

| 箇所 | 現状 | 問題 |
|---|---|---|
| `elastic_notebook/core/notebook/restore_notebook.py`（`shell.user_ns` への代入とセル再実行） | デバイス配置の確認・制御なし | 復元先デバイスの解決ポリシーが存在しない。GPU OOM時のハンドリングなし |

---

## 4. 設計方針の決定

### 4.1 アプローチの選択: フレームワークレベル（変数単位）を主軸とする

先行研究調査（§7）で整理した設計空間の3層のうち、**(A) フレームワークレベルの変数単位シリアライズ**を主軸として採用する。

| 選択肢 | 判断 | 理由 |
|---|---|---|
| **(A) フレームワークレベル**（torch/CuPyのシリアライズ機構 + カスタムreducer） | ✅ **採用** | 変数単位の選択性（migrate-vs-recompute）が保てる唯一の層。既存アーキテクチャ（dill + min-cutオプティマイザ）の自然な拡張で済む。異種環境への復元（U2–U4）が可能。CUDAコンテキスト等の捕捉不能状態はフレームワークの遅延初期化に任せられる |
| **(B) CUDA APIレベル**（Singularity/CRAC型のAPI横取り） | ❌ 不採用 | 定常オーバーヘッドと保守コスト（CUDAバージョン追従）が研究プロトタイプとして過大。CRIUgpu論文でも欠点が実証されている |
| **(C) ドライバレベル**（cuda-checkpoint/CRIUgpu） | 🔶 **U5限定の補助として将来検討** | 変数選択性がなく全GPUメモリを対象とするため主軸にはならないが、「同一マシンでのGPU一時解放」（U5）には純正機構として最適。Phase 3で検討 |

**採用根拠の核心**: CRIUgpuの実測（LLaMA 8BのC/Rに77秒・56GB）が示す通り、GPU全量C/Rは高価である。一方、Modalの実務知見「KVキャッシュのような再生成が速い大容量バッファは除外して再生成する方が速い」はまさにmigrate-vs-recompute判断であり、ElasticKernelの変数選択的アプローチはGPU時代にこそ価値が増す。この選択性は(A)の層でしか実現できない。

### 4.2 主要な設計判断

#### 判断1: GPU変数の保存形式 — 「ホスト化 + デバイスタグ分離」方式

CUDAテンソルをそのままdillに渡す（PyTorchのデフォルトpickle挙動に任せる）のではなく、**保存時に明示的にホストへ転送し（`.cpu()` / `cupy.asnumpy()`）、元のデバイス情報を別メタデータとして保存する**。

- 理由1（正しさ）: デフォルトのpickle挙動は「保存元と同じデバイスに復元」をデータ内に焼き込むため、復元先デバイスが異なると失敗する。`torch.load` の `map_location` に相当する自由度を素のdillで得るには、デバイスタグをデータから分離する必要がある。
- 理由2（コスト計測）: d2h転送を明示的なステップにすることで、転送時間を個別に計測でき、コストモデルのプロファイルと突き合わせられる。
- 理由3（互換性）: ホスト化後のオブジェクトは純粋なCPUオブジェクトなので、既存のシリアライズ・復元パスをそのまま通る。

実現手段は、dillのdispatch tableへの `torch.Tensor` / `torch.nn.Module` / `cupy.ndarray` 用カスタムreducer登録を基本とする（NFR1のため、reducer登録は `sys.modules` に torch/cupy が既にロードされている場合のみ行う）。

#### 判断2: 変更検出 — 段階的アプローチ（保守的 → 精密）

GPUテンソルの内容ハッシュはホスト転送を伴うため、セル毎の変更検出には使えない（NFR2）。以下の2段階とする：

- **第1段階（保守的）**: GPUテンソルを新クラス `GpuResidentObj`（既存の `UncomparableObj` の拡張、デバイスタグとGPUバイト数を保持）として扱う。既存のフィンガープリント機構は `UncomparableObj` に対して「入力変数としてアクセスされたら変更されたとみなす」という保守的な判定を既に持っており（`fingerprint.py` の uncomparable パス）、このパスに乗せれば**最小の変更で正しさが得られる**。欠点は偽陽性（実際は変更されていないGPU変数の再保存）。
- **第2段階（精密）**: PyTorchの `tensor._version`（in-place変更でインクリメントされるバージョンカウンタ）によるO(1)変更検出、またはGPU上での軽量リダクション（チェックサム計算をGPUカーネルで実行し、スカラのみホストへ転送）を導入する。これは研究的貢献の一部となる（§1.3）。

#### 判断3: コストモデル — 2段階転送モデルへの拡張

ElasticNotebookのコスト式を以下のように拡張する：

```
従来:  wM(x) = α·wstore(x) + wload(x)
拡張:  wM(x) = α·(w_d2h(x) + w_ser(x) + w_write(x)) + (w_read(x) + w_deser(x) + w_h2d(x))

  w_d2h(x) = gpu_size(x) / B_pcie_d2h   （GPU→CPU転送。CPU変数では0）
  w_h2d(x) = gpu_size(x) / B_pcie_h2d   （CPU→GPU転送。復元先がCPUなら0）
  B_pcie はテスト転送による動的プロファイル（既存のディスク速度プロファイルと同じ枠組み）
```

ZeRO-Infinityの知見（§5）の通り、PCIe帯域（実効10–25GB/s）はディスク帯域（実効1–3GB/s）より1桁速いため、一次近似ではGPU変数のマイグレーションコストもディスクI/Oが支配する。したがって**d2h/h2d項の追加は既存のmin-cut定式化を変えず、エッジ容量の計算式だけを変える**形で実現できる（`optimizer_exact.py:88` のエッジ容量計算に項を足すだけ）。

再計算コスト側は質的な変更が必要：

```
従来:  wR(c) = cell_runtime(c)
拡張:  wR(c) = cell_runtime(c)                  （復元先にGPUがある、またはGPU不要セル）
       wR(c) = ∞                                 （GPU必須セルで復元先にGPUがない）
```

「GPU必須セル」の判定は、セル実行後にGPU常駐変数を新規作成・変更したかどうかで近似する（`CellExecution.uses_gpu` フラグ、§5.4）。

#### 判断4: 復元デバイスの解決 — ポリシーベースの `map_location` 相当機構

復元時に各GPU変数の配置先を以下の優先順位で解決する `DevicePlacementPolicy` を導入する：

1. 保存時と同じデバイスが存在する → そこへ（U1）
2. 同種でないがGPUが存在する → カレント/指定GPUへ読み替え（U4）
3. GPUが存在しない → ポリシーにより分岐（U2）:
   - `fallback_cpu`: CPUテンソルとして復元（デフォルト。分析の続行は可能だが、再実行時の挙動差に注意）
   - `recompute`: 変数を捨て、GPUが再び使える環境でセル再計算に委ねる
   - `fail`: エラーとして報告

ポリシーはカーネル設定（環境変数 `ELASTIC_KERNEL_GPU_RESTORE_POLICY` 等）で選択可能とする。

#### 判断5: スコープ — PyTorchとCuPyを対象、TensorFlow/JAXは対象外

- PyTorch（テンソル・`nn.Module`・オプティマイザ状態・RNG状態）とCuPy（`ndarray`・メモリプール非対応の明記）を対象とする。
- TensorFlow/JAXは、既存の `UncomparableObj` 扱い（`object_hash.py:232-240`）を維持し、「シリアライズ不能 → 再計算」フォールバックに任せる（FR6）。JAXの遅延評価・デバイス配列はreduceプロトコルの挙動が大きく異なり、対応コストに見合わない。
- マルチGPU・分散（NCCL）は対象外（CRIUgpuですら未対応。単一ノード・単一プロセスのノートブックが対象）。

---

## 5. 詳細設計

### 5.1 GPUオブジェクトの検出と抽象化（新規モジュール）

`elastic_notebook/core/gpu/` を新設し、GPU関連ロジックを集約する：

```
elastic_notebook/core/gpu/
├── __init__.py
├── detect.py        # GPUオブジェクト判定・デバイス情報取得（torch/cupy非import方式）
├── reducers.py      # dill dispatch table用カスタムreducer
├── placement.py     # DevicePlacementPolicy（復元先デバイス解決）
├── profile_pcie.py  # PCIe帯域プロファイラ
└── rng.py           # GPU RNG状態の取得・復元
```

**`detect.py`**: 既存の `is_torch_tensor`（`object_hash.py:125-136`）と同じ「importせずに `__module__` で判定」方式を踏襲し、以下を提供する：

```python
def get_device_info(obj) -> DeviceInfo | None:
    """GPUオブジェクトなら DeviceInfo(device='cuda:0', nbytes=..., framework='torch')
    を返す。CPUオブジェクトなら None。torch/cupy がロードされていなければ常に None。"""
```

- torchテンソル: `obj.is_cuda` / `obj.device` / `obj.untyped_storage().nbytes()` を参照
- `nn.Module`: パラメータ・バッファを走査して集計
- CuPy: `obj.device.id` / `obj.nbytes` を参照
- **NFR1の担保**: `sys.modules` チェックを必ず先行させ、GPU非搭載環境（torch未ロード）では即 `None` を返す

**`reducers.py`**: dillのdispatch tableに登録するreducer。保存時の動作：

1. `torch.cuda.synchronize()`（計測の正確性と転送の完全性のため）
2. `cpu_obj = obj.cpu()` / `cupy.asnumpy(obj)` でホスト化（d2h時間を計測してログ）
3. `(cpu_obj, DeviceInfo)` のペアとしてシリアライズ
4. 復元側のreducerは `DevicePlacementPolicy` に従って `cpu_obj.to(resolved_device)` を実行

`nn.Module` は `state_dict` ベースではなくオブジェクトグラフごと（dillの再帰に任せ、内部のテンソルだけreducerが処理）とする。これにより既存のID graphとの整合性を保つ。オプティマイザ（`torch.optim.*`）の `state` 内のCUDAテンソルも同じreducerが再帰的に処理する。Kishuの知見に従い、モデルとオプティマイザのように同一テンソルを共有するオブジェクト群は既存のlinked variable機構（`optimizer_exact.py:102-104` のoverlapping VS制約）で同一グループとして扱われることを確認する。

### 5.2 フィンガープリント・変更検出の拡張

**`object_hash.py` の変更**:

- `construct_object_hash` の先頭近くで `get_device_info(obj)` を呼び、GPU常駐なら `GpuResidentObj(device, nbytes, version_counter)` を返す（`np.ascontiguousarray` によるホスト転送パスに**入れない**）。
- `GpuResidentObj` は `UncomparableObj` のサブクラスとし、既存の比較不能パス（`fingerprint.py:147-151` 周辺）にそのまま乗せる。

```python
class GpuResidentObj(UncomparableObj):
    def __init__(self, device: str, gpu_nbytes: int, version: int | None):
        self.device = device          # "cuda:0"
        self.gpu_nbytes = gpu_nbytes  # 実GPUメモリ消費
        self.version = version        # torch._version（取得可能な場合）

    def __eq__(self, other):
        # 第2段階: version が両方取得できていれば精密比較、
        # できなければ UncomparableObj と同じ保守的判定にフォールバック
        ...
```

- 第1段階では `__eq__` は常に「比較不能」を返し、入力としてアクセスされたGPU変数は変更扱いになる（保守的・正しい）。
- 第2段階で `tensor._version` 比較を有効化し、偽陽性を削減する。`_version` はin-place演算でのみ増えるため、「同一オブジェクトの再代入なし変更」を捕捉できる。out-of-place演算で別オブジェクトになるケースは既存のID graph機構が捕捉する。

**`id_graph.py` の変更（第2段階）**: `IdGraphNode` に `data_ptr`（`tensor.data_ptr()`）をオプションフィールドとして追加し、GPUバッファを共有するビュー同士のエイリアシングを検出可能にする。

### 5.3 コストモデルの拡張

**`profile_variable_size.py`**: `get_memory_size` の先頭で `get_device_info(obj)` を呼び、GPUオブジェクトなら `nbytes` をそのまま加算する（`sys.getsizeof` を使わない）。これによりFR2を満たす。

**`profile_pcie.py`（新規）**: 既存の `profile_migration_speed.py` と同じ枠組みで、起動時（GPU検出時のみ）に小さなテストテンソルのd2h/h2d転送を計測し、`B_pcie_d2h` / `B_pcie_h2d` を推定する。計測には `torch.cuda.synchronize()` を挟む。キャッシュ効果を避けるため、複数サイズ（1MB/16MB/64MB程度）で計測して回帰する。

**`variable_snapshot.py`**: フィールド追加。

```python
class VariableSnapshot:
    ...
    self.size = 0          # 既存: ホスト側サイズ
    self.gpu_size = 0      # 新規: GPUメモリ上のバイト数（CPU変数は0）
    self.device = None     # 新規: "cuda:0" 等（CPU変数はNone）
```

**`cell_execution.py`**: フィールド追加。

```python
class CellExecution:
    ...
    self.cell_runtime = ...   # 既存（CUDA同期込みに修正、§5.4）
    self.uses_gpu = False     # 新規: このセルがGPU常駐変数を生成・変更したか
```

**`optimizer_exact.py`**: エッジ容量の計算式のみ変更（min-cut構造は不変）。

```python
# source → VS エッジ（migration cost）
migration_cost = (
    active_vs.size / self.migration_speed_bps
    + active_vs.gpu_size / self.pcie_d2h_bps          # 保存時 d2h
    + active_vs.gpu_size / self.pcie_h2d_bps          # 復元時 h2d
)

# CE → sink エッジ（recomputation cost）
recomputation_cost = (
    np.inf if (ce.uses_gpu and not target_has_gpu)    # 復元先デバイス可用性
    else ce.cell_runtime
)
```

`target_has_gpu` は、チェックポイント保存時には不明な場合がある（移行先が決まっていない）。デフォルトは「同種環境への復元」を仮定して `True` とし、移行先が既知の場合に設定で上書きできるようにする。**復元先環境が保存時の想定と異なっていた場合の再計画（保存済みチェックポイントに対し、復元時にオプティマイザの判断を再評価する）は将来課題**とする（§7）。

### 5.4 カーネル層の変更

**`elastic_kernel/kernel.py` の `do_execute`**:

- セル実行時間計測の前後に、GPUがアクティブな場合のみ `torch.cuda.synchronize()` を挿入する（`sys.modules` に torch があり `torch.cuda.is_initialized()` の場合のみ。NFR1）。これにより `cell_runtime` がGPU計算を含む実時間になる。
- 同期自体のオーバーヘッドは非同期実行のメリットを一部削るが、セル境界での同期はJupyterの体感に実質影響しない（セル出力の表示自体が同期点になるため）。

**RNG状態の記録（`gpu/rng.py`）**: セル実行前に `torch.get_rng_state()` / `torch.cuda.get_rng_state_all()` / CuPyの状態を取得し、`CellExecution` に紐づけて記録する。復元時のセル再計算前に該当状態を `set_rng_state` で巻き戻すことで、再計算の決定性を高める（`torch.utils.checkpoint` の `set_device_states` が先例）。RNG状態は数KB程度なので常時記録してもコストは無視できる。

### 5.5 復元層の変更

**`recover.py` / `restore_notebook.py`**:

1. メタデータ読み込み後、保存時のデバイス構成と現環境（`torch.cuda.device_count()` 等）を突き合わせ、`DevicePlacementPolicy` を初期化する。
2. 変数のデシリアライズ時、reducerがポリシーに従って配置先を解決する（§4.2 判断4）。
3. **GPU OOMハンドリング**: h2d転送で `torch.cuda.OutOfMemoryError` が出た場合、(a) その変数をCPUに残す、(b) 警告ログ、の順で縮退する。復元順序は「小さいGPU変数から」とし、巨大変数のOOMが他の変数の復元を巻き込まないようにする。
4. **例外の分類**: 既存の「あらゆるunpickle失敗 → 再計算」（`recover.py:40-51`）に、CUDA関連例外（デバイス不在・OOM・コンテキストエラー）の分類とログ出力を追加する。挙動は従来どおり再計算フォールバックだが、原因をユーザーが追えるようにする。

### 5.6 チェックポイントフォーマット

- メタデータに `format_version` と `gpu_metadata`（保存時のデバイス構成、PCIeプロファイル結果、各変数のDeviceInfo）を追加する。
- `gpu_metadata` がないチェックポイント（旧フォーマット）は従来どおり読み込める（NFR3）。
- GPU変数のペイロードはホスト化済みデータなので、ファイルフォーマット自体（dillの順次dump）は変えない。

### 5.7 全体像（保存・復元フロー）

```
【保存（do_shutdown時）】
1. ディスク帯域プロファイル（既存） + PCIe帯域プロファイル（新規・GPU検出時のみ）
2. 各変数のサイズ計測 — GPU変数は nbytes で計測（変更）
3. min-cutオプティマイザ — migration costにd2h/h2d項、GPU必須セルの再計算コスト分岐（変更）
4. migrate対象のシリアライズ — GPUテンソルはreducerがd2h → デバイスタグ分離保存（新規）
5. メタデータ（依存グラフ + gpu_metadata + RNG状態）保存（拡張）

【復元（カーネル起動時）】
1. メタデータ読み込み、デバイス構成の突き合わせ、PlacementPolicy初期化（新規）
2. migrate変数のデシリアライズ — reducerがポリシーに従いh2d（新規）、OOM時はCPU縮退
3. recompute対象セルの再実行 — 実行前にRNG状態を巻き戻し（新規）
4. 依存グラフ状態の復元（既存）
```

---

## 6. 段階的実装計画

実装は行わないが、着手時のロードマップとして段階を定義する。各Phaseは独立に評価可能な単位とする。

### Phase 0: 正しさの土台（GPU変数で壊れないようにする）

- `gpu/detect.py`（デバイス検出）と `GpuResidentObj`（保守的フィンガープリント）
- `profile_variable_size.py` のGPUサイズ計測（FR2）
- `recover.py` のCUDA例外分類・ログ
- **ゴール**: GPUノートブックでカーネルがクラッシュ・誤動作せず、GPU変数が（非効率でも）保守的に再計算へ回ること

### Phase 1: GPU変数のマイグレーション（U1）

- `gpu/reducers.py`（ホスト化 + デバイスタグ分離）と dill dispatch table 統合
- `gpu/placement.py`（同一デバイス復元のみ）
- `do_execute` のCUDA同期による正確な `cell_runtime`
- **ゴール**: 同一GPUマシンでのセッション再開で、GPU変数がmigrate対象として保存・復元されること

### Phase 2: コストモデル統合と異種環境復元（U2–U4）

- `gpu/profile_pcie.py` とオプティマイザのコスト式拡張（FR3, FR4）
- `DevicePlacementPolicy` の全ポリシー（`fallback_cpu` / `recompute` / `fail`）
- RNG状態の記録・巻き戻し（FR5）
- 第2段階の変更検出（`_version` カウンタ）
- **ゴール**: GPU→CPU移行を含むベンチマークで、migrate-vs-recomputeの判断がGPUコストを正しく反映すること

### Phase 3（オプション）: 弾力的GPU利用（U5）と発展

- cuda-checkpointによるプロセスレベルGPU解放との併用検討（同一マシン・アイドル時）
- GPU上の軽量チェックサムによる精密変更検出
- CheckFreq式 snapshot(d2h)-then-persist(disk) の非同期化によるセル単位自動チェックポイント

---

## 7. 未解決課題とリスク

| # | 課題 | 影響 | 対応方針 |
|---|---|---|---|
| R1 | **保存時に復元先環境が不明**な場合、`target_has_gpu` の仮定が外れるとオプティマイザの判断が最適でなくなる | 中 | デフォルトは同種環境仮定。将来課題として「復元時の再計画」（メタデータに全セルのコスト情報を残し、復元側で再最適化）を検討。これは研究ネタにもなる |
| R2 | **GPUメモリの二重消費**: d2hでホスト側にコピーを作るため、保存時に変数サイズ分のホストRAMが必要 | 中 | 変数を1つずつ処理して逐次解放する。`filesystem_adapter.py` のストリーミング化も将来検討 |
| R3 | **`_version` カウンタの限界**: `data_ptr` 経由の生ポインタ操作や外部ライブラリのin-place変更は捕捉できない | 低 | 第1段階の保守的判定をフォールバックとして残す |
| R4 | **CuPyのメモリプール・カレントデバイス依存**: 復元後のメモリプール状態は再現されない（性能のみに影響、正しさには影響しない） | 低 | ドキュメントに明記。プールはCuPyが自然に再構築する |
| R5 | **非決定的GPU演算**: RNG状態を巻き戻しても、cuDNNの非決定的アルゴリズム等により再計算結果がビット一致しない場合がある | 中 | ElasticNotebookと同様、完全な決定性は保証対象外とする。RNG巻き戻しは「決定性を高める」ベストエフォートと位置づける |
| R6 | **巨大モデル（数十GB）のチェックポイント時間**: d2h + ディスク書込で分オーダーになりうる | 中 | まさにオプティマイザが解くべき問題（HuggingFaceからロードしたモデルなら「再ロード（=セル再実行）」が選ばれるはず）。評価で検証する |
| R7 | **torch/cupyのバージョン追従**: `_version` / `untyped_storage` 等の内部APIへの依存 | 低 | 内部API依存箇所を `gpu/` モジュールに集約し、バージョンガードを付ける |

---

## 8. 評価計画

研究プロジェクトとして、以下の評価を想定する：

### 8.1 ベンチマークワークロード

- **DL学習ノートブック**: データロード（CPU）→ 前処理（CPU）→ モデル定義・学習（GPU）→ 評価・可視化（混在）。Kaggle等の実ノートブックを改変して使用
- **推論・分析ノートブック**: 事前学習モデルのロード（GPU）→ バッチ推論 → 結果分析（CPU）
- 変数構成の異なるパターン: 巨大モデル+小データ / 小モデル+巨大中間テンソル / 再計算が高価な学習済み状態

### 8.2 比較対象

1. **Baseline-A: 全再計算**（GPU変数を全て捨てる = 現状のElasticKernelの実質的挙動）
2. **Baseline-B: 全マイグレート**（naiveなtorch.save相当、選択性なし）
3. **Baseline-C: cuda-checkpoint / CRIUgpu**（プロセス全量C/R。同一マシン制約下でのみ）
4. **提案手法**（GPU対応コストモデル + 選択的マイグレーション）

### 8.3 測定指標

- チェックポイント時間 / 復元時間 / チェックポイントサイズ
- セル実行オーバーヘッド（NFR2の検証: フィンガープリンティングのコスト）
- 異種環境復元の成功率と縮退挙動（U2: GPU→CPU移行）
- コストモデルの精度（予測マイグレーション時間 vs 実測）

### 8.4 期待される主張

- 「GPU変数のmigrate-vs-recompute選択により、全量C/R（CRIUgpu系）比でチェックポイントサイズ・時間を大幅削減できる」
- 「デバイスタグ分離方式により、プロセスレベルC/Rでは不可能な異種環境（GPU→CPU）復元が可能」
- 「PCIe帯域を含む2段階コストモデルは、ディスクのみのモデルよりGPUワークロードで最適に近い判断を下す」

---

## 付録: 参考文献（要約は [gpu_support_prior_work.md](./gpu_support_prior_work.md) を参照）

- ElasticNotebook (VLDB 2023): https://arxiv.org/abs/2309.11083
- Kishu (VLDB 2025): https://www.vldb.org/pvldb/vol18/p970-li.pdf
- NVIDIA cuda-checkpoint: https://github.com/NVIDIA/cuda-checkpoint
- CRIUgpu (2025): https://arxiv.org/abs/2502.16631
- Singularity (Microsoft, 2022): https://arxiv.org/abs/2202.07848
- PhoenixOS (SOSP 2025): https://arxiv.org/abs/2405.12079
- CheckFreq (FAST 2021): https://www.usenix.org/conference/fast21/presentation/mohan
- Check-N-Run (NSDI 2022): https://www.usenix.org/conference/nsdi22/presentation/eisenman
- Gemini (SOSP 2023): https://dl.acm.org/doi/10.1145/3600006.3613145
- Checkmate (MLSys 2020): https://arxiv.org/abs/1910.02653
- DTR (ICLR 2021): https://arxiv.org/abs/2006.09616
- ZeRO-Infinity (2021): https://arxiv.org/pdf/2104.07857
- Gandiva (OSDI 2018): https://www.usenix.org/system/files/osdi18-xiao.pdf
- Run:ai GPU Memory Swap: https://run-ai-docs.nvidia.com/saas/platform-management/runai-scheduler/resource-optimization/memory-swap
- Modal GPU Memory Snapshots: https://modal.com/blog/gpu-mem-snapshots
- PyTorch CUDA deserialize issue: https://github.com/pytorch/pytorch/issues/16797
