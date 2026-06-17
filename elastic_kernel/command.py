import sys
from pathlib import Path


def install_kernel():
    try:
        import os

        from jupyter_client.kernelspec import install_kernel_spec

        import elastic_kernel
    except ImportError:
        print("jupyter_clientまたはelastic_kernelがインストールされていません。")
        return False

    # elastic_kernelパッケージの実際のパスを取得
    kernel_dir = Path(os.path.dirname(elastic_kernel.__file__))
    install_kernel_spec(
        str(kernel_dir), kernel_name="elastic_kernel", user=True, replace=True
    )
    print(f"Elastic Kernel installed from: {kernel_dir}")
    return True


def enable_server_extension():
    """外部オーケストレーター向け REST API（Jupyter Server 拡張）を有効化する。

    拡張の有効化は jpserver_extensions config の書き込みで決まるため、
    toggle_server_extension_python で sys.prefix 配下の config に書き込む。
    jupyter_server が未導入の場合は extras の案内をして False を返す。
    """
    try:
        from jupyter_server.extension.serverextension import (
            toggle_server_extension_python,
        )
    except ImportError:
        print(
            "jupyter_server がインストールされていません。"
            "REST API を使うには `pip install elastic_kernel[server]` を実行してください。",
            file=sys.stderr,
        )
        return False

    toggle_server_extension_python(
        "elastic_kernel.serverextension", enabled=True, sys_prefix=True
    )
    print(
        "Elastic Kernel server extension enabled "
        "(POST /elastic_kernel/checkpoint, /restore)."
    )
    return True


def main():
    args = sys.argv[1:]
    if args and args[0] == "install":
        install_kernel()
        # `--server` 指定時のみ REST API（サーバー拡張）も有効化する。
        if "--server" in args[1:]:
            enable_server_extension()
    else:
        print("Usage: elastic-kernel install [--server]", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
