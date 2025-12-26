import sys
from pathlib import Path

from setuptools.command.install import install


def install_kernel():
    try:
        import os

        from jupyter_client.kernelspec import install_kernel_spec

        import rerun_kernel
    except ImportError:
        print("jupyter_clientまたはrerun_kernelがインストールされていません。")
        return False

    # rerun_kernelパッケージの実際のパスを取得
    kernel_dir = Path(os.path.dirname(rerun_kernel.__file__))
    install_kernel_spec(
        str(kernel_dir), kernel_name="rerun_kernel", user=True, replace=True
    )
    print(f"Rerun Kernel installed from: {kernel_dir}")
    return True


class PostInstallCommand(install):
    def run(self):
        install.run(self)
        print("=== Rerun Kernel: Installing Jupyter kernel ===")
        install_kernel()


def main():
    if len(sys.argv) > 1 and sys.argv[1] == "install":
        install_kernel()
    else:
        print("Usage: rerun-kernel install", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
