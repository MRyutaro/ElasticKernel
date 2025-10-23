import sys
from pathlib import Path

from setuptools.command.install import install


def install_kernel():
    try:
        import os

        from jupyter_client.kernelspec import install_kernel_spec

        import ipykernel4exp
    except ImportError:
        print("jupyter_clientまたはelastic_kernelがインストールされていません。")
        return False

    # elastic_kernelパッケージの実際のパスを取得
    kernel_dir = Path(os.path.dirname(ipykernel4exp.__file__))
    install_kernel_spec(
        str(kernel_dir), kernel_name="ipykernel4exp", user=True, replace=True
    )
    print(f"ipykernel4exp installed from: {kernel_dir}")
    return True


class PostInstallCommand(install):
    def run(self):
        install.run(self)
        print("=== ipykernel4exp: Installing Jupyter kernel ===")
        install_kernel()


def main():
    if len(sys.argv) > 1 and sys.argv[1] == "install":
        install_kernel()
    else:
        print("Usage: ipykernel4exp install", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
