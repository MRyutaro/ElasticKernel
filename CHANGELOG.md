# Changelog

## [0.2.1](https://github.com/MRyutaro/ElasticKernel/compare/v0.2.0...v0.2.1) (2026-06-18)


### Performance Improvements

* prewarm migration-speed profiling off the checkpoint critical path ([6898811](https://github.com/MRyutaro/ElasticKernel/commit/68988115f6e60af9b5db508e26822dfaccab60ec))
* prewarm migration-speed profiling off the checkpoint critical path ([6a60f3d](https://github.com/MRyutaro/ElasticKernel/commit/6a60f3db421c8e749b3adeb86c9fadfe3bd61bdd))


### Documentation

* add GPU support (Issue [#75](https://github.com/MRyutaro/ElasticKernel/issues/75)) prior-art survey ([4fe8875](https://github.com/MRyutaro/ElasticKernel/commit/4fe88755d428fe974e8dd898ad7e1dde4d8e88d1))

## [0.2.0](https://github.com/MRyutaro/ElasticKernel/compare/v0.1.2...v0.2.0) (2026-06-18)


### Features

* add ELASTIC_KERNEL_AUTO_CHECKPOINT to toggle auto checkpoint/restore ([47dff77](https://github.com/MRyutaro/ElasticKernel/commit/47dff77bbbd7163bc17e91bb1003ca663723e9de))
* GET /elastic_kernel/auto_mode で現在モードを照会できるようにする ([6e39538](https://github.com/MRyutaro/ElasticKernel/commit/6e395380b07717eb8087ac6d1f3e50e7aa1a5d5a))
* 自動保存/復元モードを実行時に切り替える control / REST を追加 ([7947fe6](https://github.com/MRyutaro/ElasticKernel/commit/7947fe6968586aa8c380c9b5b57064af2de702ae))
* 自動保存/復元を起動時(env)で個別に、停止時の自動保存は実行時(REST/control)でも切替可能に ([d7049b8](https://github.com/MRyutaro/ElasticKernel/commit/d7049b8c0eb2ca060a856a09978e446b5f48eafe))


### Documentation

* PR 本文に変更ファイル一覧を書かない方針を CLAUDE.md に追記 ([561563a](https://github.com/MRyutaro/ElasticKernel/commit/561563a54c505795a054b3c9a693e27ae85eb804))
* server 拡張有効化メッセージに auto_mode を追記 ([99e929a](https://github.com/MRyutaro/ElasticKernel/commit/99e929ad71eca53ef8cd929a7e7fcd1a96a17f51))
* 復元の枠組みを「先起動＋任意タイミング明示復元」に修正 ([de09e9f](https://github.com/MRyutaro/ElasticKernel/commit/de09e9ff63feeca771572a8ae0b91cee33874d78))

## [0.1.2](https://github.com/MRyutaro/ElasticKernel/compare/v0.1.1...v0.1.2) (2026-06-17)


### Documentation

* document post-merge cleanup steps in CLAUDE.md ([81c286d](https://github.com/MRyutaro/ElasticKernel/commit/81c286d92b813538ef9322d22b6ce78883814aa9))
* document post-merge cleanup steps in CLAUDE.md ([7d2fc77](https://github.com/MRyutaro/ElasticKernel/commit/7d2fc77dbef481d4fd056230eb3d14f6d10a0429))
* keep feature-experiment branch (cleanup exception) ([1d68702](https://github.com/MRyutaro/ElasticKernel/commit/1d6870241f8acc43eaf883d3999d7a3896cc6c5f))

## [0.1.1](https://github.com/MRyutaro/ElasticKernel/compare/v0.1.0...v0.1.1) (2026-06-17)


### Miscellaneous Chores

* release 0.1.1 ([288bb48](https://github.com/MRyutaro/ElasticKernel/commit/288bb4867b21e7a69cb5e9e0418d3cd1b02442b1))

## [0.1.0](https://github.com/MRyutaro/ElasticKernel/compare/v0.0.34...v0.1.0) (2026-06-17)


### Features

* add on-demand checkpoint/restore API for external orchestrators ([8c0baba](https://github.com/MRyutaro/ElasticKernel/commit/8c0babaf30f16def846e8045cb4c4fa3a8b1dba4))
* add on-demand checkpoint/restore API for external orchestrators ([7599e2e](https://github.com/MRyutaro/ElasticKernel/commit/7599e2efaf2547f261b771f9563562340977e89c))


### Bug Fixes

* prevent kernel crash when JPY_SESSION_NAME is unset ([a22c0ad](https://github.com/MRyutaro/ElasticKernel/commit/a22c0ada654c45aaa185b8966d34aa8ef3ed17af))
* prevent kernel crash when JPY_SESSION_NAME is unset ([6c6f087](https://github.com/MRyutaro/ElasticKernel/commit/6c6f08723b93c49eff84c3d6bb505590949fc5b5)), closes [#15](https://github.com/MRyutaro/ElasticKernel/issues/15)


### Documentation

* clarify _run_on_main_loop docstring (control vs main loop marshaling) ([986b173](https://github.com/MRyutaro/ElasticKernel/commit/986b1733a7e7a2e7634306054f2c7c0a189aee10))
* document the on-demand checkpoint/restore API ([3239260](https://github.com/MRyutaro/ElasticKernel/commit/3239260f088858033654e0874905435005c176cc))

## [0.0.34](https://github.com/MRyutaro/ElasticKernel/compare/v0.0.33...v0.0.34) (2026-06-15)


### Bug Fixes

* hash datetime64 arrays in object_hash instead of crashing ([ded6738](https://github.com/MRyutaro/ElasticKernel/commit/ded67389ad7ba55ecbf328e449732b14f8b1c834))
* hash datetime64 arrays in object_hash instead of crashing ([6423d66](https://github.com/MRyutaro/ElasticKernel/commit/6423d669af5f992248506151b6588e9215d8927c)), closes [#60](https://github.com/MRyutaro/ElasticKernel/issues/60)

## [0.0.33](https://github.com/MRyutaro/ElasticKernel/compare/v0.0.32...v0.0.33) (2026-06-14)


### Bug Fixes

* record cells mixing magic lines with Python code ([#17](https://github.com/MRyutaro/ElasticKernel/issues/17)) ([90bbba7](https://github.com/MRyutaro/ElasticKernel/commit/90bbba705846a4cc11156f36bd01be36036b5c43))
* record cells mixing magic lines with Python code ([#17](https://github.com/MRyutaro/ElasticKernel/issues/17)) ([4afff90](https://github.com/MRyutaro/ElasticKernel/commit/4afff904204fe6f9169ad7adcd73d3558b2abe16))
* stabilize migration speed measurement to prevent runaway checkpoints ([a89627e](https://github.com/MRyutaro/ElasticKernel/commit/a89627e349600e38b4a171a2902e906fbc9c3875))
* stabilize migration speed measurement to prevent runaway checkpoints ([ba32944](https://github.com/MRyutaro/ElasticKernel/commit/ba32944c880cafc51654df40e32157eb24a57a5b)), closes [#21](https://github.com/MRyutaro/ElasticKernel/issues/21)


### Performance Improvements

* profile migration speed only once per session ([288b8e4](https://github.com/MRyutaro/ElasticKernel/commit/288b8e400b89587cdfed0e266976635958cae6bf)), closes [#21](https://github.com/MRyutaro/ElasticKernel/issues/21)

## [0.0.32](https://github.com/MRyutaro/ElasticKernel/compare/v0.0.31...v0.0.32) (2026-06-14)


### Documentation

* fix min-cut comment and add worktree/PR guidance to CLAUDE.md ([cae7203](https://github.com/MRyutaro/ElasticKernel/commit/cae72030015daa45ebb2728e2bbe5bc99a315f74))

## [0.0.31](https://github.com/MRyutaro/ElasticKernel/compare/v0.0.30...v0.0.31) (2026-06-14)


### Documentation

* fix misleading min-cut comment in optimizer_exact ([d710be4](https://github.com/MRyutaro/ElasticKernel/commit/d710be45fe9a4df208eea4dbfd668107d7ee8291))
* fix misleading min-cut comment in optimizer_exact ([b11662c](https://github.com/MRyutaro/ElasticKernel/commit/b11662c4555003ed321ce05b5e8c12605fdd91d1))

## [0.0.30](https://github.com/MRyutaro/ElasticKernel/compare/v0.0.29...v0.0.30) (2026-06-14)


### Documentation

* use user-attachments URLs for inline demo video playback ([08279a0](https://github.com/MRyutaro/ElasticKernel/commit/08279a05cfeae4e2fa22bb31f36fbbc38dfb3690))
* use user-attachments URLs for inline demo video playback ([dc9ad14](https://github.com/MRyutaro/ElasticKernel/commit/dc9ad14eaf007225ee6e02e23a67e20f4709393a))

## [0.0.29](https://github.com/MRyutaro/ElasticKernel/compare/v0.0.28...v0.0.29) (2026-06-14)


### Bug Fixes

* checkpointのoverlapping判定にfingerprint存在ガードを追加 (D-12) ([a48fbf2](https://github.com/MRyutaro/ElasticKernel/commit/a48fbf24b02270383897f6e1087bab3c146ff50d))
* **kernel:** 暗黙のサブモジュールimport明示化とskip判定の重複解消 (D-6, D-8前半) ([d520673](https://github.com/MRyutaro/ElasticKernel/commit/d520673c8a9f5522a40ff1d8be6e259a919d027b))
* profile_variable_sizeでカスタムクラスの属性を測定 (D-4, ★サイズ推定変更) ([27d66de](https://github.com/MRyutaro/ElasticKernel/commit/27d66de075f8c7c8787eee703df6f861bd012a12))
* **profile:** os.systemのrm/mkdirをshutil/os.makedirsに置換 (D-11前半) ([6fce372](https://github.com/MRyutaro/ElasticKernel/commit/6fce372d3bd21aa5c78e62e255418e256b1a3697))
* read速度計測で実際にread()する (D-11後半, ★migration_speed変更) ([c0fdef6](https://github.com/MRyutaro/ElasticKernel/commit/c0fdef62a348fdb43bfe8d33bc0f3191d3219e5a))
* リファクタリング Phase 3 — 安全なコード修正（挙動同一）(D-6/D-8/D-11) ([3746a0e](https://github.com/MRyutaro/ElasticKernel/commit/3746a0e30e6c49acb638b75a610ea41552e621e7))
* 復元後マジックコマンドのみ実行→shutdown時のKeyErrorを修正 ([#26](https://github.com/MRyutaro/ElasticKernel/issues/26)) ([923d8e0](https://github.com/MRyutaro/ElasticKernel/commit/923d8e05de13a18fa796009cdf3389f107a647ad))
* 復元後マジックコマンドのみ実行→shutdown時のKeyErrorを修正 ([#26](https://github.com/MRyutaro/ElasticKernel/issues/26)) ([035790e](https://github.com/MRyutaro/ElasticKernel/commit/035790e87ee9966d915f48f8e6672864c8fbd8f1))


### Documentation

* add ipykernel vs ElasticKernel demo videos to README ([1046b67](https://github.com/MRyutaro/ElasticKernel/commit/1046b67d7bb495594667f6d998fdb145b998bdb9))
* add ipykernel vs ElasticKernel demo videos to README ([51ea4b5](https://github.com/MRyutaro/ElasticKernel/commit/51ea4b5939dfb1bc3550b23f4846776a17d6010a))
* CLAUDE.mdの実態乖離を修正 (D-10) ([6cdf04f](https://github.com/MRyutaro/ElasticKernel/commit/6cdf04f14dfc972160e3357c93210b059a357756))
* DEVELOPERS.mdの今後の課題をGitHub issue化し本文から削除 ([d23c197](https://github.com/MRyutaro/ElasticKernel/commit/d23c1972d71771141306f3f07320a7ad212d36a3))
* コピペ痕の docstring 修正 "Raw cell cell." -&gt; "The raw cell source code." (D-14) ([91da0b6](https://github.com/MRyutaro/ElasticKernel/commit/91da0b6012d2433869394cd553567480724e491e))
