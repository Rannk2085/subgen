#!/usr/bin/env python3
"""
subgen 入口
直接被 ./subgen 启动脚本调用，不应被 import
"""
import sys
from pathlib import Path

# 把 src/ 加入 sys.path，让模块之间可以平铺 import
SRC_DIR = Path(__file__).resolve().parent
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

# 必须 ≥ 3.11（tomllib 标准库）
if sys.version_info < (3, 11):
    print("ERROR: subgen 需要 Python 3.11+")
    print(f"  当前: {sys.version}")
    sys.exit(1)


def main() -> int:
    import cli
    return cli.main(sys.argv[1:])


if __name__ == "__main__":
    sys.exit(main())
