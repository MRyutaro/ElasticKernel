#!/bin/bash

# 引数の数をチェック (必須)
if [ "$#" -ne 2 ]; then
    echo "Usage: $0 <root_dir> <kernels_dir>"
    echo "Example: $0 /path/to/my/root /path/to/my/kernels"
    exit 1 # エラーで終了
fi

ROOT_DIR="$1"
KERNELS_DIR="$2"

# ディレクトリの存在チェック (推奨)
if [ ! -d "$ROOT_DIR" ]; then
    echo "Error: ROOT_DIR '$ROOT_DIR' does not exist."
    exit 1
fi

if [ ! -d "$KERNELS_DIR" ]; then
    echo "Error: KERNELS_DIR '$KERNELS_DIR' does not exist."
    exit 1
fi

echo ROOT_DIR: $ROOT_DIR
echo KERNELS_DIR: $KERNELS_DIR


# KERNELS_DIRでforを回す
for kernel in `ls $KERNELS_DIR`; do
    # python3はスキップ
    if [ $kernel = "python3" ]; then
        continue
    fi
    # それ以外は削除
    rm -rf $KERNELS_DIR/$kernel
done

# $ROOT_DIR/kernelsでforを回す
for kernel in `ls $ROOT_DIR/kernels`; do
    # kernel.jsonがなかったらスキップ
    if [ ! -e $ROOT_DIR/kernels/$kernel/kernel.json ]; then
        echo "kernel.json not found: $kernel"
        continue
    fi
    # カーネルをコピー
    mkdir $KERNELS_DIR/$kernel
    cp $ROOT_DIR/kernels/$kernel/kernel.json $KERNELS_DIR/$kernel

    # kernel.pyがなかったらスキップ
    if [ ! -e $ROOT_DIR/kernels/$kernel/kernel.py ]; then
        echo "kernel.py not found: $kernel"
        continue
    fi
    cp $ROOT_DIR/kernels/$kernel/kernel.py $KERNELS_DIR/$kernel
done

jupyter kernelspec list
