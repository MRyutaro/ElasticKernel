# GPU対応（Issue #75）先行研究調査

> **位置づけ:** 未発表研究。private リポジトリ `MRyutaro/ElasticKernel-GPU` 専用。公開リポジトリへは発表後に取り込む。
> **調査日:** 2026-06-18
> **調査手法:** マルチソース Web 検索 → 一次資料フェッチ → 主張の敵対的検証（3票/主張、2/3で棄却）→ 引用付き統合。
> **検証統計:** 5観点 / 21 一次資料 / 97 主張抽出 → 25 主張を検証 → **25 確認・0 棄却**（全主張が 3-0 の全会一致）。

---

## 0. エグゼクティブサマリ

ElasticKernel の基盤である **ElasticNotebook (VLDB 2024)** をGPU対応させるための先行研究は、次の5領域に豊富に存在する。

1. GPU常駐テンソルの**シリアライズ・移送**（変数粒度）
2. GPUプロセスの**チェックポイント／マイグレーション**（プロセス粒度）
3. DLジョブの **checkpoint-restart**（オンライン・パイプライン化）
4. Jupyter／対話的計算の**状態保存・復元・移行**
5. **保存 vs 再計算**のコストトレードオフ最適化（lineage / materialization）

**核心となる事実:**

- **ElasticNotebook 自身は GPU 状態を捕捉しない。** 論文は比較対象の OS-level チェックポイントを「メモリのみ（GPU不可）」と明記し、さらに **「GPU を持つマシンへライブセッションを移行する」ことを動機例として挙げている**。つまり Issue #75「GPU対応」が埋めるべきギャップは、基盤論文の上で裏付けられている。
- ElasticKernel の migrate-vs-recompute 判定は **Application History Graph (AHG) 上の min-cut 問題** `w(S) = w_M(S) + w_R(X−S)` として定式化され、移送コスト `w_M` は **変数サイズ × Profiler が測るストレージ帯域** から推定される。**GPU対応の核心はこの Profiler に「GPU↔ホスト／ディスク転送速度」次元を追加し、デバイス常駐オブジェクトを識別・移送・再計算コスト評価できるようにすること。**

**実装の3系統（直接の手本）:**

| 系統 | 代表研究 | 粒度 | ElasticKernel への適合 |
|---|---|---|---|
| (a) プロセスレベル GPU スナップショット | cuda-checkpoint, CRIUgpu, CRAC, Singularity | プロセス全体 | 変数粒度の選択的 migrate と相性が悪いが、GPU→host 転送実測値・サイズ削減手法の根拠 |
| (b) GPU→CPU 二段転送のプロファイル＆パイプライン | CheckFreq, DataStates-LLM, Fastensor | テンソル群 | **二段コストモデルへの拡張を強く支持。** Profiler 拡張の直接の手本 |
| (c) `__reduce__` で on-GPU テンソルをシリアライズ | **Kishu** | 変数（Co-variable） | **最も自然。** ElasticKernel の dill/pickle 移送路線を裏付け |

とくに **CheckFreq の `snapshot()`/`persist()` 二相モデル** と **Kishu の reduction 方式**が、ElasticKernel の「変数ごとに GPU→host 転送して移送 vs 再計算」という二段コストモデルへの拡張を強く支持する。

---

## 1. 拡張対象：ElasticKernel（ElasticNotebook）のコストモデル

> 出典: ElasticNotebook, *PVLDB Vol.17* — https://www.vldb.org/pvldb/vol17/p119-li.pdf

GPU 対応で「どこをいじるか」を明確にするため、まず拡張対象のコストモデルを押さえる。

- **定式化:** migrate-vs-recompute 判定は AHG 上の **min-cut 問題** `w(S) = w_M(S) + w_R(X−S)` に還元される。`S` がマイグレート集合、`X−S` が再計算集合。〔3-0 確認〕
- **移送コスト `w_M`:** `w_M(S) = Σ (α × w_store(x) + w_load(x))`。store/load 時間は **変数サイズ** と **Profiler が測るストレージの遅延／帯域** から推定。`α` 係数が suspension 前の store 時間を割り引く。**シリアライズ不可能な変数はコスト無限大**（=必ず再計算側）。〔3-0 確認〕
- **Profiler:** チェックポイント直前に Cost Model を完成させ、**変数サイズ** と **ストレージへの network 帯域** をプロファイル、**cell runtime はセッション中に監視・記録**。評価環境では帯域 **274 MB/s**、read 遅延 **175 µs**。〔3-0 確認〕

**→ GPU拡張の統合点:** この Profiler のプロファイリング・フックこそが「GPU↔ホスト転送速度プロファイリング」を足す場所。現行は cell runtime / 変数サイズ / network 帯域しか測っていない。GPU 常駐変数は migrate 経路で **GPU→host→disk** の転送を要するため、コストモデルに **GPU↔host 転送項**を追加する必要がある。

---

## 2. GPU常駐オブジェクトのシリアライズ・スナップショット（変数粒度）

### 2.1 Kishu — `__reduce__` による on-GPU テンソルの変数粒度シリアライズ【最重要】

> 出典: Kishu, *PVLDB Vol.18* — https://www.vldb.org/pvldb/vol18/p970-li.pdf

ElasticNotebook 系列の関連システム。OS-level メモリダンプではなく **Pickle の `__reduce__` reduction** で **Co-variable 単位**にシリアライズする。

- 「`unlike CRIU, Kishu utilizes reductions to store Co-variables, hence it can store distributed or off-CPU data (e.g., Ray's dataset or on-GPU tensors)`」を逐語確認。
- **146 のデータサイエンスライブラリ全クラスで time-travel に成功**し、CRIU/DumpSession が失敗する 6 クラス（multiprocessing/off-CPU を含む、`torch.tensor`/`tf.tensor` 等）を扱えた。〔3-0 確認〕
- ⚠️ 注意: 6 クラスは厳密には **CRIU の失敗に対応**（DumpSession は別の 7 unserializable クラス）。

**→ ElasticKernel への含意:** 「dill/pickle で GPU テンソルを host 経由で移送する」路線を直接裏付ける最重要の先行研究。ElasticKernel の既存シリアライズ基盤（dill）の延長で GPU テンソルを変数粒度で扱える可能性が高い。**変数粒度の選択的 migrate-vs-recompute を保ったまま GPU 対応する最有力アプローチ。**

### 2.2 Fastensor — 転送手段をテンソル毎に適応選択（GPUDirect Storage）

> 出典: Fastensor, *ACM TACO 2024* — https://dl.acm.org/doi/10.1145/3630108

- **NVIDIA GPUDirect Storage (GDS)** で NVMe SSD↔GPU メモリ間のテンソル転送を直接化（host 経由を省く）。〔3-0 確認〕
- **訓練初期数 iteration の適応探索**で生成した辞書から、テンソルの block サイズと runtime context に応じて **最適な転送ツールをテンソル毎に候補集合から選択**。〔3-0 確認〕

**→ ElasticKernel への含意:** 「初期に転送速度をプロファイルしてテンソル毎に最適手段を選ぶ」発想は ElasticKernel の Profiler 拡張・migrate 経路選択に直接対応。**GDS により GPU↔ディスク直接転送で host 経由をスキップするコスト削減オプション**も示唆。

### 2.3 補助的に確認した周辺技術（個別の検証 finding には未昇格・参考）

- **safetensors**（HuggingFace, PyTorch Foundation 入り）: テンソル専用の安全・高速シリアライズ形式。GPU テンソルの永続化フォーマット候補。
- **CuPy interoperability**（`__cuda_array_interface__` / DLPack）: フレームワーク間で GPU バッファをゼロコピー共有する標準。GPU 常駐オブジェクトの識別・受け渡しの基盤。

---

## 3. GPUプロセスのチェックポイント／マイグレーション（プロセス粒度）

### 3.1 NVIDIA cuda-checkpoint — CRIU を補完する CUDA プロセス suspend/restore

> 出典: NVIDIA Developer Blog / GitHub — https://developer.nvidia.com/blog/checkpointing-cuda-applications-with-criu/ , https://github.com/NVIDIA/cuda-checkpoint

- **suspend:** CUDA API を lock → 投入済み作業を完了 → **device memory をドライバ管理の host 割当へコピー** → GPU リソース解放。**restore:** GPU 再取得 → device memory を元アドレスへ復元 → stream/context 等の CUDA オブジェクト復元 → API unlock。〔3-0 確認〕
- 「`A suspended CUDA process no longer directly refers to any GPU hardware at the OS level and may therefore be checkpointed by ... CRIU`」を逐語確認。**CRIU 単体は NVIDIA GPU リソースを管理できない**ため cuda-checkpoint が必要。〔3-0 確認〕
- ⚠️ 時間依存性: **driver 550+ 前提**。

**→ ElasticKernel への含意:** 変数粒度ではなく**プロセス丸ごと保存する代替/補完**。直接採用は変数粒度モデルと相性が悪いが、**GPU memory→host 転送コストの実測値の根拠**になる。

### 3.2 CRIUgpu — 透過的な CPU-GPU 統合スナップショット【プロセス系の最有力】

> 出典: arXiv 2502.16631 — https://arxiv.org/pdf/2502.16631

- GPU ドライバのチェックポイント機能（cuda-checkpoint 統合 + AMD ROCm）を使い、**アプリ無改造・再コンパイル不要**な **CUDA/ROCm 両対応の透過的 CPU-GPU 統合スナップショット**を実現。〔3-0 確認〕
- **API interception / log-and-replay を使わない**ため**定常状態（checkpoint 間）のオーバーヘッドをゼロ**化し、復元時間も短縮。**CRIU 4.0 に upstream 済み**。〔3-0 確認〕
- ⚠️ 制約（2025時点・時間依存）: driver 550+ / x64 / UVM・IPC memory・NCCL 未対応。

**→ ElasticKernel への含意:** プロセスレベルで GPU 状態を保存する最有力手段。「カーネルプロセスごと丸ごと退避」する運用（ElasticHub の zero-reload マイグレーションのような上位レイヤ）と組み合わせる場合の候補。

### 3.3 CRAC — split-process アーキテクチャ（低オーバーヘッド）

> 出典: CRAC, *SC20* — https://www.khoury.northeastern.edu/home/gene/papers/sc20.pdf

- **単一プロセス内で** アプリコード（チェックポイント対象=upper half）と外部 CUDA ライブラリ/runtime（非対象=lower half）を**同一アドレス空間に分離**。プロキシ方式（CRUM の 6–12%）の IPC オーバーヘッドを排し **約 1% 以下**の実行時オーバーヘッド。CUDA streams/UVM 対応。〔3-0 確認〕
- ⚠️ 1% は計算律速 CUDA アプリでの値、数値は同一研究グループの自己報告。

**→ ElasticKernel への含意:** GPU プロセス透過チェックポイントの歴史的基盤。低オーバーヘッド化の設計知見。

### 3.4 Microsoft Singularity — device-proxy アーキテクチャ

> 出典: arXiv 2202.07848 — https://arxiv.org/pdf/2202.07848

- GPU 呼出を LD_PRELOAD で**別アドレス空間の per-device プロキシ**へ転送し、ホストプロセスをデバイス固有マッピングから分離 → 既存 CRIU でホストプロセスを checkpoint/migrate 可能に（CRIU は本来 GPU 使用プロセスの device mapping を扱えない）。〔3-0 確認〕
- **GPU デバイス状態は device-proxy が device-to-host memcpy で保存**。**メモリアロケータ (SAInt) 制御で「実使用領域のみ」保存しチェックポイントサイズを削減**。〔3-0 確認〕
- 復元時のポインタ無効化を防ぐため**起動時に GPU 全メモリを占有し常に同一 CPU アドレスへ map**、opaque デバイスハンドル（`cudaStreamCreate` 等）も**仮想化**してマイグレーション間の同一性を維持。〔3-0 確認〕

**→ ElasticKernel への含意:** 2つの設計教訓が直接関連 — ①**アロケータ認識で実使用 GPU 領域のみ移送しサイズ削減**（= 移送コスト `w_M` の削減）、②**ハンドル/ポインタ同一性の維持**（= 復元後の整合性）。⚠️ 同一性維持は再仮想化であり bit-identical な復元ではない。

---

## 4. DLジョブの checkpoint-restart（オンライン・パイプライン化）

### 4.1 CheckFreq — `snapshot()`/`persist()` 二相 + オンライン頻度最適化【コストモデルの直接の手本】

> 出典: CheckFreq, *USENIX FAST21* — https://www.usenix.org/system/files/fast21-mohan.pdf

- GPU メモリ常駐のモデル重み/optimizer 状態を、epoch 境界でなく **iteration 粒度**で **二相機構**でチェックポイント:
  - **`snapshot()`** = モデルパラメータを **GPU→CPU メモリへコピー**
  - **`persist()`** = 非同期で**ディスクへ書く**
  - snapshot は重み更新後に取得し、次の重み更新までの計算と**パイプライン化**。〔3-0 確認〕
- checkpoint 頻度を **モデルサイズ / storage 帯域 / iteration 時間のオンライン・プロファイリング**で自動決定、**adaptive rate tuning** でオーバーヘッドを上限（目標 5%、実測 3.5% 以内）に抑える。〔3-0 確認〕

**→ ElasticKernel への含意（最重要の設計示唆）:** GPU 常駐オブジェクトの migrate 経路は **GPU→host 転送（GPU↔CPU 帯域）** と **CPU→disk 書込** を**別々にプロファイルすべき**で、これが**二段コストモデル**を支持する。オンライン・プロファイリングでオーバーヘッドを動的に上限内へ抑える発想は、ElasticNotebook の Profiler / `α` 係数と整合する。

### 4.2 DataStates-LLM — immutable 期間を利用した非同期コピー

> 出典: DataStates-LLM, *HPDC24* — https://arxiv.org/pdf/2406.10707

- LLM チェックポイントは GPU 常駐のモデル/optimizer 状態を永続ストレージへコピーする処理で、**素朴な同期直書きが大きな I/O オーバーヘッドを生み訓練を停止**させる。〔3-0 確認〕
- モデル/optimizer 状態テンソルが**長期間 immutable** である性質を利用し、その内容を**背景で遅延非同期コピー**して干渉を最小化。〔3-0 確認〕

**→ ElasticKernel への含意:** GPU→disk 直書きコストの大きさと、**immutable 期間を利用した非同期/遅延移送によるコスト隠蔽**の有効性。⚠️ フルモデル訓練向けで、対話的カーネルの変数粒度 migrate-vs-recompute とは粒度が異なる背景知見。

---

## 5. Jupyter／対話的計算の状態保存・復元・移行

- **ElasticNotebook (VLDB 2024)** — 本プロジェクトの基盤。§1 参照。GPU を未対応次元かつ動機シナリオとして明記（§0）。
- **Kishu (VLDB 2025)** — §2.1 参照。on-GPU テンソルを変数粒度で扱える唯一の対話的システム系の先行研究。
- 関連（参考、個別検証は未実施）: arXiv 2406.13856（Jupyter state 系）等。

**→ この領域の要点:** 対話的計算で GPU 状態まで含めて「変数粒度・選択的」に保存・復元・移行できることを示しているのは実質 **Kishu** のみ。ElasticKernel の差別化は **Kishu の GPU テンソル移送能力**に **ElasticNotebook の migrate-vs-recompute コスト最適化**を掛け合わせる点にある（＝両者の系列を統合する位置づけ）。

---

## 6. 「保存 vs 再計算」のコストトレードオフ最適化（lineage / materialization）

ElasticKernel の核である「保存 vs 再計算」の最適化は、DL／ML 分野でも独立に研究されている。以下は **save vs recompute 観点で収集した一次資料**（統合段階で個別 finding には未昇格、背景・設計参考として記載）。

| 研究 | 出典 | 関連 |
|---|---|---|
| Checkmate | arXiv 1910.02653 | DNN 訓練の**再計算 vs 保持（rematerialization）を最適化**。GPU メモリ制約下で「中間活性化を保存するか再計算するか」を ILP で解く——ElasticKernel の min-cut と同型の問題を**GPU メモリ軸**で解く先行例 |
| materialization/recompute 最適化 | arXiv 2309.11083 | 反復 ML の中間結果の materialize vs recompute |
| 中間結果の保存最適化 | ACM 10.1145/3514221.3526186 | materialization 戦略 |
| lineage/再計算 | EDBT 2025 (mboehm7) | https://mboehm7.github.io/resources/edbt2025.pdf |
| MISTIQUE | Semantic Scholar | モデル中間結果の保存・クエリ。保存 vs 再計算のサイズ/コスト判断 |
| HELIX | ResearchGate | 反復 ML の holistic 最適化（materialize vs recompute） |

**→ ElasticKernel への含意:** とくに **Checkmate** は「GPU メモリ予算の下での保存 vs 再計算」を最適化問題として解いており、**GPU 計算の再実行コスト**（= ElasticKernel の `w_R` の GPU 版）をどう見積もるかの直接の参考になる。

---

## 7. ElasticKernel への統合方針（まとめ）

調査結果を ElasticKernel のアーキテクチャ（`elastic_notebook/core/`）に対応づけると、GPU 対応で手を入れるべきは次の3点。

### (1) Profiler への GPU 転送プロファイリング次元の追加 — `algorithm/` + checkpoint 前処理

- 現行は **cell runtime / 変数サイズ / ストレージ帯域** のみ（§1）。ここに **GPU↔host 帯域**（および GDS 利用時は GPU↔disk 帯域）を追加する。
- 手本: **CheckFreq のオンライン・プロファイリング**（§4.1）、**Fastensor の初期 iteration 適応探索**（§2.2）。
- 移送コストを **`w_M^GPU(x) = w_{GPU→host}(x) + α × w_store(x) + w_load(x)`** のように**二段**に拡張するのが自然（CheckFreq の二相 `snapshot()`/`persist()` に対応）。

### (2) GPU常駐オブジェクトの識別・移送 — `core/mutation/`（fingerprint）+ `core/io/migrate.py`

- 移送は **Kishu 流の `__reduce__`/dill で host 経由シリアライズ**（§2.1）が変数粒度モデルと最も整合。既存の dill 基盤の延長で実装可能性が高い。
- **フィンガープリント（mutation detection）が未解決**: 現行の `id_graph` + `object_hash`(xxhash) が GPU テンソルに対し **device→host コピーを伴わずに安定したハッシュ・同一性判定**ができるか要検証（§8 Open Q2）。
- サイズ削減の教訓: **Singularity のアロケータ認識（実使用領域のみ移送）**（§3.4）。

### (3) GPU計算の再実行コストのモデル化 — `algorithm/optimizer_exact.py`（`w_R`）

- セル実行時間に GPU カーネル起動・データ転送が含まれる場合の `w_R` 推定。手本: **Checkmate**（§6）。
- ⚠️ **再計算は復元先に GPU がある前提が崩れうる**（動機例は「GPU マシンへ移行」＝移行元に GPU が無い場合がある）。再計算可否のデバイス依存性をコストモデルに織り込む必要（§8 Open Q4）。

### 補足: プロセスレベル代替（上位レイヤ）

変数粒度が困難なケース（multiprocessing/分散/NCCL 等、Kishu でも `__reduce__` 不能なオブジェクト）には、**cuda-checkpoint / CRIUgpu でカーネルプロセスごと退避**する代替経路（§3）を、ElasticHub の zero-reload マイグレーション運用と組み合わせる設計も検討余地がある。

---

## 8. Open Questions（今後の検討課題）

1. **移送経路の選択:** (a) Kishu 流 `__reduce__`/dill で host 経由 serialize、(b) cuda-checkpoint/CRIUgpu 流のプロセスレベル GPU スナップショット、(c) Fastensor 流の GDS で GPU↔ディスク直接転送 — のどれを採るか。変数粒度の選択的 migrate-vs-recompute を保つには (a) が自然だが、**GPU→host 転送コストと再計算コストの実測比較**が必要。
2. **GPU テンソルのフィンガープリント:** 現行 `id_graph` + `object_hash`(xxhash) は GPU テンソルに対し **device→host コピー無し**で安定ハッシュ・同一性判定できるか。device メモリ上で直接計算できるか（`tensor.data_ptr`/storage 識別の利用可否）は未解明。
3. **Profiler の測定タイミング:** GPU↔host/ディスク転送速度を CheckFreq のように**セッション中に動的測定**すべきか、チェックポイント直前の**一回測定**で足りるか。GPU メモリ圧迫下（space-sharing）での測定値の安定性も要検証。
4. **再計算コストとデバイス依存性:** セル再実行に GPU カーネル起動・転送が含まれる場合の `w_R` 推定。さらに**再計算時に復元先で GPU が利用可能とは限らない**状況（GPU マシンへの移行）での再計算可否の扱いが未整理。

---

## 9. Caveats（調査上の注意）

全 25 主張は 3-0 の全会一致で一次資料（VLDB/SC20/FAST/HPDC/TACO 論文、NVIDIA 公式 doc、arXiv）に基づき検証済みで信頼度は総じて高い。ただし:

1. **時間依存性:** cuda-checkpoint / CRIUgpu は driver 550+・x64・UVM/IPC/NCCL 未対応（2025–2026 時点）等の scope 限定があり、GPU モデルや driver バージョンで可否が変わる。今後のドライバ更新で制約が緩む可能性が高い。
2. **過剰表現の補正:** 「ElasticNotebook は明示的に GPU 非対応と述べている」は厳密には**比較対象の OS-level ツールを指す記述**で、自己言及としてはやや強い（ただし GPU が未対応次元・動機シナリオである点は正しい）。Kishu の「6 クラス」は厳密には CRIU の失敗に対応（DumpSession は別の 7 unserializable クラス）。
3. **粒度の違い:** CheckFreq / DataStates-LLM / Fastensor はフルモデル訓練向けで GPU 常駐状態全体を扱い、ElasticKernel の対話的・変数粒度の migrate-vs-recompute とは粒度が異なる。背景知見・コストモデル設計の参考として有効だが、そのまま転用はできない。
4. **性能数値の出所:** 一部は同一研究グループの自己報告（CRAC 1%、CRUM 6–12%）。
5. **同一性維持の限界:** device-handle/ポインタ同一性維持（Singularity）はマイグレーション先での再仮想化であり、bit-identical な復元ではない。

---

## 10. 参考文献

**一次資料（finding として検証済み）**

- ElasticNotebook, *PVLDB Vol.17* — https://www.vldb.org/pvldb/vol17/p119-li.pdf
- Kishu, *PVLDB Vol.18* — https://www.vldb.org/pvldb/vol18/p970-li.pdf
- NVIDIA cuda-checkpoint（Blog / GitHub）— https://developer.nvidia.com/blog/checkpointing-cuda-applications-with-criu/ , https://github.com/NVIDIA/cuda-checkpoint
- CRIUgpu, *arXiv 2502.16631* — https://arxiv.org/pdf/2502.16631
- CRAC, *SC20* — https://www.khoury.northeastern.edu/home/gene/papers/sc20.pdf
- Microsoft Singularity, *arXiv 2202.07848* — https://arxiv.org/pdf/2202.07848
- CheckFreq, *USENIX FAST21* — https://www.usenix.org/system/files/fast21-mohan.pdf
- DataStates-LLM, *HPDC24* — https://arxiv.org/pdf/2406.10707
- Fastensor, *ACM TACO 2024* — https://dl.acm.org/doi/10.1145/3630108

**保存 vs 再計算（背景・参考、個別検証は未実施）**

- Checkmate, *arXiv 1910.02653* — https://arxiv.org/abs/1910.02653
- materialize vs recompute, *arXiv 2309.11083* — https://arxiv.org/abs/2309.11083
- 中間結果の保存最適化, *ACM 10.1145/3514221.3526186* — https://dl.acm.org/doi/10.1145/3514221.3526186
- lineage/再計算, *EDBT 2025* — https://mboehm7.github.io/resources/edbt2025.pdf
- MISTIQUE — https://www.semanticscholar.org/paper/MISTIQUE...
- HELIX — https://www.researchgate.net/publication/331390284_HELIX...

**周辺技術（参考）**

- safetensors（PyTorch Foundation）— https://huggingface.co/blog/safetensors-joins-pytorch-foundation
- CuPy interoperability — https://docs.cupy.dev/en/stable/user_guide/interoperability.html
