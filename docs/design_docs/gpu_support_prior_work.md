# GPU対応のための先行研究調査

本ドキュメントは、ElasticKernelをGPU対応させるための設計（[gpu_support_design.md](./gpu_support_design.md)）の根拠となる先行研究調査をまとめたものである。

調査日: 2026-06-12

---

## 目次

1. [ノートブック状態チェックポインティング研究](#1-ノートブック状態チェックポインティング研究)
2. [透過的GPUチェックポインティングシステム](#2-透過的gpuチェックポインティングシステム)
3. [フレームワークレベルのGPU状態シリアライズ](#3-フレームワークレベルのgpu状態シリアライズ)
4. [ML学習チェックポインティング研究](#4-ml学習チェックポインティング研究)
5. [データ配置・転送のコストモデル](#5-データ配置転送のコストモデル)
6. [JupyterにおけるGPU共有・弾力的GPU利用](#6-jupyterにおけるgpu共有弾力的gpu利用)
7. [総合: 設計空間の整理と結論](#7-総合-設計空間の整理と結論)

---

## 1. ノートブック状態チェックポインティング研究

### ElasticNotebook (VLDB 2023)

- URL: https://arxiv.org/abs/2309.11083 / https://github.com/illinoisdata/ElasticNotebook
- **機構**: 本プロジェクトの直接の基盤。セル実行を透過的に監視してApplication History Graph (AHG)を構築し、変数とセル実行の依存関係を記録する。マイグレーションコスト `wM(S) = Σ(α·wstore(x) + wload(x))` と再計算コスト `wR(S) = Σ wrun(c)` の和を最小化する分割を最小カット最適化で求める。マイグレーション速度はストレージへのテスト書き込みでプロファイルする。
- **GPUへの言及**: GPUは「GPUのあるマシンへセッションを移行したい」という**動機付けとしてのみ**登場する。OSレベルチェックポインティングの欠点として「GPU等のデバイス状態を保存できない」と指摘するが、ElasticNotebook自身もGPU状態は未対応。シリアライズ不能な変数はコストを∞にして再計算側に強制し、デシリアライズ失敗時はAHGをたどって必要セルのみ再実行するフォールバックを持つ。
- **教訓**: 「シリアライズ不能 → コスト∞ → 再計算」という既存の枠組みは、GPU変数に対して「GPU→CPU転送コスト + シリアライズコスト」という**有限の新コスト項**を導入する形で自然に拡張できる。

### Kishu (VLDB 2025)

- URL: https://www.vldb.org/pvldb/vol18/p970-li.pdf / https://github.com/illinoisdata/kishu
- **機構**: 同じUIUCグループの後続研究。ノートブック状態のGitライクなタイムトラベル（commit/checkout）。ポインタ参照で連結したオブジェクト群を「Co-variable」という粒度で扱い、セル実行ごとに変化したCo-variableのみの差分を増分保存する。
- **GPUへの言及**: PyTorchを含む146クラスと互換と主張し、on-GPU tensorもPythonのreduceプロトコル経由で扱えるとするが、**GPUメモリ状態そのものの保存方法（デバイス間転送コスト、RNG、CUDAコンテキスト）は論文中で詳細化されていない**。実質的にはPyTorchのpickle機構に依存していると推察される。
- **教訓**: フレームワークのreduceプロトコルに乗るだけでもGPUテンソルの「データ」は救えるが、それを明示的なコストモデル（PCIe転送）や復元先デバイスの差異と結びつけた研究は**この系譜に存在せず、本プロジェクトの新規性となりうる**。

**領域1の結論**: ElasticNotebook/Kishu系でGPU状態を一級市民として扱った後続研究は見つからなかった。(a) GPU変数のフィンガープリンティング、(b) GPU→CPU転送帯域を含むコストモデル、(c) デバイス可用性が変わった場合の復元、はいずれも未解決の研究課題である。

---

## 2. 透過的GPUチェックポインティングシステム

### NVIDIA cuda-checkpoint + CUDA Checkpoint/Restore API (2024–)

- URL: https://github.com/NVIDIA/cuda-checkpoint / https://docs.nvidia.com/cuda/cuda-driver-api/group__CUDA__CHECKPOINT.html
- **機構**: ドライバ純正機能（r550+、Linux x64のみ）。プロセス単位でCUDA状態をrunning↔suspendedにトグルする。suspend時は (1)CUDA APIをロック (2)投入済みワークの完了を待機 (3)デバイスメモリをドライバ管理でホストへ退避 (4)GPUリソースを完全解放。resume時はメモリを元のアドレスにマップし直し、ストリーム・コンテキスト等を再構築する。CRIUと組み合わせてプロセス全体のC/Rが可能。
- **限界**: UVM・CUDA IPCメモリ未対応。復元には基本的に同種GPUが必要。変数単位の選択性はない。
- **教訓**: 「GPUを解放したいがプロセスは生かしたい」というJupyterの要件に最も近い純正機構。変数単位シリアライズと**相補的**に使える。

### CRIUgpu (arXiv 2025)

- URL: https://arxiv.org/abs/2502.16631 / https://criu.org/GPU_Checkpointing
- **機構**: CRIUのCUDAプラグインとしてcuda-checkpointを統合し、CPU+GPUの統一スナップショットを作成。API横取り方式と異なり定常時オーバーヘッドゼロ。
- **実測値（H100）**: GPT-2 1.5B: checkpoint 88.8s / restore 43.4s / サイズ60.1GB。LLaMA 3.1 8B: 77.4s / 38.8s / 55.9GB。**GPUメモリ全量のC/Rは数十秒〜分オーダーで、数十GBのイメージを生む**。
- **限界**: NCCL未対応、復元には同一GPU種・同一順序が必要、変数選択性なし。
- **教訓**: 「全部マイグレート」のベースラインコストの実測データとして有用。GPUメモリ→ディスクの実効帯域は ≈0.7–1.4 GB/s オーダー。変数選択的アプローチの動機付けになる。

### Singularity (Microsoft, arXiv 2022)

- URL: https://arxiv.org/abs/2202.07848
- **機構**: デバイスプロキシ（API横取り）でCUDAランタイム/ドライバAPIコールをログし、復元時にリプレイしてGPU状態を再構築。未修整のDNNジョブを透過的にプリエンプト・マイグレート可能にする。
- **限界**: API横取りに伴う定常オーバーヘッドと保守コスト（CUDAバージョン追従、fatbinaryの解析）。CRIUgpu論文がこの方式の欠点を実証的に批判している。
- **教訓**: API横取り方式は研究プロトタイプとしては実装・保守コストが過大。ドライバ純正機能がある現在、新規にこの路線を採る理由は薄い。

### CRAC (SC'20) / Cricket (CCPE 2022)

- URL: https://www.ccs.neu.edu/home/gene/papers/sc20.pdf / https://onlinelibrary.wiley.com/doi/full/10.1002/cpe.6474
- **機構**: CRACはDMTCPプラグインでCUDA関連コールをリプレイしてGPU状態を再構築（UVM対応が特徴）。CricketはGPU側とCPU側をRPCで分離する仮想化層。
- **限界**: APIラッパの網羅性問題、カーネル実行中のC/R不可。PyTorch級の巨大ライブラリでは実用に耐えない。

### PhoenixOS (SOSP 2025)

- URL: https://arxiv.org/abs/2405.12079 / https://github.com/SJTU-IPADS/PhoenixOS
- **機構**: GPUプロセスの**並行**C/Rを実現する初のOSサービス。GPUにはdirty bit/CoWがないため、カーネル起動引数からメモリアクセスを投機的に推定し、バイナリ計装で実行時検証する。cuda-checkpoint比でstop-the-worldを回避。
- **教訓**: 「実行を止めずにチェックポイント」はノートブックでも魅力的（セル実行中のバックグラウンド保存）だが、研究プロトタイプとしては過剰。将来課題として引用価値が高い。

---

## 3. フレームワークレベルのGPU状態シリアライズ

### torch.save / torch.load / pickle挙動

- URL: https://docs.pytorch.org/docs/main/generated/torch.load.html / https://github.com/pytorch/pytorch/issues/16797
- **挙動**: CUDAテンソルはpicklable。シリアライズ時にストレージはホストへコピーされ**デバイスタグ（例: `cuda:0`）と共に保存**され、デシリアライズ時はCPU上に復元してから**保存元と同じデバイスへ移動**される。`torch.load` の `map_location` でデバイス再配置が可能だが、**素のpickle/dillには `map_location` に相当する仕組みがない**。CUDA非搭載（または該当デバイス欠如）環境では `RuntimeError: Attempting to deserialize object on a CUDA device but torch.cuda.is_available() is False` で失敗する。
- **ElasticKernelへの含意**: 現行のdillベース実装はCUDAテンソルを「一応」保存できるが、(a) 復元先にGPUがない/デバイス番号が違うと失敗する、(b) GPU→CPUコピー時間がコストモデルでプロファイルされない、という2つの穴がある。dillのdispatch tableに `torch.Tensor` 用reducerを登録し、`map_location` 相当の復元ポリシーを実装するのが定石。

### CuPy

- URL: https://docs.cupy.dev/en/stable/reference/generated/cupy.ndarray.html
- `cupy.ndarray` もpickle対応（ホストにコピーして保存、復元時は**カレントデバイス**に確保）。PyTorchと違いデバイスタグの厳密な復元ではなくカレントデバイス依存のため、復元時のデバイスコンテキスト管理が必要。

### フレームワークレベルで捕捉できない状態

以下は原理的に捕捉不能であり、復元時に再生成する設計が必要：

- CUDAコンテキスト、ストリーム/イベント
- cuDNN/cuBLASハンドル
- コンパイル済みカーネル（JITキャッシュ）
- メモリプール状態（PyTorch caching allocator / CuPy memory pool）
- NCCLコミュニケータ

**重要**: これらはPyTorch/CuPyが遅延初期化するため、変数単位アプローチでは「データだけ復元し、コンテキストは初回利用時に自然再生成」で済む。これが**プロセスレベルC/Rに対する変数レベルアプローチの本質的な利点**である。

### RNG状態

- URL: https://docs.pytorch.org/docs/stable/generated/torch.cuda.get_rng_state.html
- `torch.get_rng_state()`（CPU）と `torch.cuda.get_rng_state(device)`（GPU）は**別管理**で両方の保存・復元が必要。`torch.utils.checkpoint` 自体がデバイスRNGの保存/復元（`set_device_states`）を行うのが先例。CuPyにも `cupy.random` のグローバル状態がある。再計算戦略の決定性を保証するには、セル実行前のRNG状態を依存グラフの一部として記録する必要がある。

---

## 4. ML学習チェックポインティング研究

| 研究 | 会場/年 | 要点 |
|---|---|---|
| **CheckFreq** | FAST 2021 | 2フェーズ方式: `snapshot()` でGPU→CPUメモリへコピー（学習は継続）、`persist()` で非同期にディスク書込。チェックポイント頻度をプロファイルに基づき自動チューニング。 https://www.usenix.org/conference/fast21/presentation/mohan |
| **Check-N-Run** | NSDI 2022 | 差分チェックポイント（更新されたパラメータのみ）+量子化で書込帯域6–17×削減。 https://www.usenix.org/conference/nsdi22/presentation/eisenman |
| **DeepFreeze** | CCGrid 2020 | 非同期・マルチレベル（メモリ階層）チェックポイント。 https://ieeexplore.ieee.org/document/9139666/ |
| **Gemini** | SOSP 2023 | チェックポイントをCPUメモリに置くことで高頻度化、復旧時間92%以上削減。 https://dl.acm.org/doi/10.1145/3600006.3613145 |
| **Just-In-Time Checkpointing** | EuroSys 2024 | 定期保存ではなく障害発生時にチェックポイント。定常オーバーヘッドほぼゼロ。 https://dl.acm.org/doi/10.1145/3627703.3650085 |

**教訓**:

1. GPU→CPU（PCIe: 実効10–25GB/s）とCPU→ディスク（実効1–3GB/s）は速度が1桁違うため、**「GPU→ホストへのスナップショット」と「ホスト→永続化」を分離した2段階コストモデル**にすべき。
2. シャットダウン時チェックポイントなら同期で十分だが、将来のセル単位自動保存ではCheckFreq式のsnapshot-then-persistが有効。
3. 差分保存（Check-N-Run/Kishu）はモデル微調整ループのあるノートブックで効く。

---

## 5. データ配置・転送のコストモデル

### Checkmate (MLSys 2020)

- URL: https://arxiv.org/abs/1910.02653
- テンソル再実体化（rematerialization）をMILPで定式化し、ハードウェア毎のプロファイルベースコストモデルで最適解を求める。「全ノード同コスト」という従来仮定を排した点が、変数毎にサイズ・再計算時間が大きく異なるノートブックの状況と同型。

### DTR (ICLR 2021) / Capuchin (ASPLOS 2020)

- URL: https://arxiv.org/abs/2006.09616
- DTRのevictionヒューリスティック `h(t) = cost(t) / (size(t) × staleness(t))` は、ElasticKernelの最適化が解いている問題のオンライン版。Capuchinはswap（転送）とrecompute（再計算）を実測アクセスパターンに基づき併用する。「PCIe転送が再計算より安い変数はswap、逆はrecompute」という判断は `OptimizerExact` のGPU拡張そのもの。

### ZeRO-Offload / ZeRO-Infinity (2021)

- URL: https://arxiv.org/pdf/2104.07857
- PCIe 3.0 x16 = 32GB/s、4.0 x16 = 64GB/s（理論値）を前提に、算術強度が低い計算はPCIe転送コストを正当化しないという形でCPU/GPU配置を決定する。
- **重要な含意**: GPU→CPU転送はディスク書込より速いので、**GPU変数のマイグレーションコストはほぼディスクI/Oで支配される**。既存のファイルシステムプロファイラを大きく変えずに、d2h項を追加するだけで一次近似としては妥当。一方、**再計算コストはGPU実行を前提とするので、復元先にGPUがない場合は再計算コスト自体が∞または大幅増になる**——コストモデルに「復元環境のデバイス可用性」という新しい次元が必要。

---

## 6. JupyterにおけるGPU共有・弾力的GPU利用

### NVIDIA Run:ai GPU Memory Swap

- URL: https://run-ai-docs.nvidia.com/saas/platform-management/runai-scheduler/resource-optimization/memory-swap
- **まさに想定ユースケースの商用実装**: 対話ノートブックがGPUを使っていない間、GPUメモリをCPUメモリへ透過的にスワップアウトし、他のワークロードにGPUを明け渡す。
- **教訓**: 「アイドルノートブックのGPU解放」には実需がある。ただしRun:aiはノードレベルのインフラであり、**変数依存グラフを知らないため全GPUメモリを盲目的にスワップする**。ElasticKernelは「再計算した方が安い変数はスワップすらしない」という選択性で差別化できる。

### Gandiva (OSDI 2018)

- URL: https://www.usenix.org/system/files/osdi18-xiao.pdf
- suspend-resume: DNN学習のGPUメモリ使用量がミニバッチ境界で10×以上変動する周期性を利用し、メモリ使用量が最小の瞬間にGPU→CPUコピーを行う。「いつチェックポイントするか」がコストを支配するという知見。ノートブックなら「セル実行の合間」が自然な最小点。

### サーバレスGPUスナップショット（Modal / NVIDIA Dynamo / vLLM）

- URL: https://modal.com/blog/gpu-mem-snapshots
- Modalはcuda-checkpoint + CPU側C/R + 遅延ロードFSで、vLLMコールドスタートを45s→5sに短縮。実務知見: (1) マルチGPU/NCCLはスナップショット困難、(2) **KVキャッシュのような「再生成が速い大容量バッファ」はチェックポイントから除外して再生成する方が速い**——これはまさにmigrate-vs-recompute判断であり、変数選択的アプローチの妥当性を産業側からも裏付ける。

---

## 7. 総合: 設計空間の整理と結論

### 設計空間の3層

| 層 | 代表 | 粒度 | migrate/recompute選択性 | デバイス可搬性 | Jupyter適合性 |
|---|---|---|---|---|---|
| **(A) フレームワークレベル**（torch/CuPyのreduce・`to()` を利用した変数単位シリアライズ） | Kishu（暗黙）, torch.save | 変数 | **あり**（オプティマイザと統合可能） | **高い**（CPUオンリー環境にも復元可） | 高い |
| **(B) CUDA APIレベル**（API横取り + ログリプレイ） | Singularity, CRAC, Cricket | プロセス | なし | 中 | 低い（定常オーバーヘッド、保守コスト大） |
| **(C) ドライバ/OSレベル** | cuda-checkpoint, CRIUgpu, PhoenixOS | プロセス全体 | なし（全GPUメモリ） | **低い**（同一GPU種が必要） | 中（GPU解放用途には有効） |

### 結論

dillベースの変数単位マイグレーション + migrate-vs-recomputeオプティマイザという既存アーキテクチャには**(A)が圧倒的に適合**する。理由:

1. **既存コストモデルの自然な拡張で済む**: `wstore` にd2h転送項を加え、GPUセルにフラグを付けるだけで一次実装が可能。
2. **選択性が保てる**: CRIUgpuの実測が示す通り全量C/Rは高価。「再計算が安い」GPU変数を捨てる判断はこの層でしかできない。
3. **デバイス可搬性**: 保存時に `.cpu()` 化 + デバイスタグをメタデータ化し、復元時にポリシーで配置先を決めれば、(C)では不可能な異種環境への復元ができる。これはElasticNotebookの「ライブマイグレーション」という本来の動機と整合する。
4. CUDAコンテキスト等の捕捉不能状態は、変数レベルでは**そもそも保存不要**（フレームワークが遅延再初期化）であり、プロセスレベルC/Rの最難関を回避できる。

補助として、「GPU解放（同一マシン・セッション継続）」ユースケースに限り cuda-checkpoint をカーネルプロセスへ適用するハイブリッド案も検討に値する（詳細は設計書を参照）。
