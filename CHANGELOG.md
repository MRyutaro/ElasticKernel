# Changelog

## [0.0.30](https://github.com/MRyutaro/ElasticKernel/compare/v0.0.29...v0.0.30) (2026-06-14)


### Documentation

* sync Japanese README video URLs and document README conventions ([7b62afd](https://github.com/MRyutaro/ElasticKernel/commit/7b62afd47f50cf1634df9473b3bfbb84b7703ff0))
* use user-attachments URLs for inline video playback in README ([5a7ff3d](https://github.com/MRyutaro/ElasticKernel/commit/5a7ff3db555a18d544c4977945c9735165951ce1))

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
