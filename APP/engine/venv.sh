#!/bin/bash
# ============================================================
# info-collector 虚拟环境管理脚本
# 用法: ./venv.sh [create|activate|install|update|clean]
# ============================================================

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VENV_DIR="$SCRIPT_DIR/.venv"
REQ_FILE="$SCRIPT_DIR/requirements.txt"

# 颜色输出
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

info()  { echo -e "${GREEN}[INFO]${NC} $1"; }
warn()  { echo -e "${YELLOW}[WARN]${NC} $1"; }
error() { echo -e "${RED}[ERROR]${NC} $1"; }

# 检查是否在 venv 中
in_venv() {
    [[ -n "$VIRTUAL_ENV" && "$VIRTUAL_ENV" == "$VENV_DIR" ]]
}

# 创建虚拟环境
cmd_create() {
    if [[ -d "$VENV_DIR" ]]; then
        warn "虚拟环境已存在: $VENV_DIR"
        read -p "是否删除重建？[y/N] " -n 1 -r; echo
        if [[ ! $REPLY =~ ^[Yy]$ ]]; then
            info "跳过创建。"
            return 0
        fi
        rm -rf "$VENV_DIR"
    fi

    info "创建虚拟环境..."
    python3 -m venv "$VENV_DIR"
    info "虚拟环境创建完成: $VENV_DIR"

    cmd_install
}

# 安装依赖
cmd_install() {
    if ! [[ -d "$VENV_DIR" ]]; then
        error "虚拟环境不存在，请先运行: ./venv.sh create"
        exit 1
    fi

    if ! [[ -f "$REQ_FILE" ]]; then
        error "requirements.txt 不存在: $REQ_FILE"
        exit 1
    fi

    info "激活虚拟环境: source $VENV_DIR/bin/activate"
    # 使用 venv 中的 pip
    "$VENV_DIR/bin/pip" install --upgrade pip
    "$VENV_DIR/bin/pip" install -r "$REQ_FILE"
    info "依赖安装完成。"
}

# 更新依赖（根据当前 requirements.txt）
cmd_update() {
    if ! [[ -d "$VENV_DIR" ]]; then
        error "虚拟环境不存在，请先运行: ./venv.sh create"
        exit 1
    fi
    info "更新依赖..."
    "$VENV_DIR/bin/pip" install --upgrade pip
    "$VENV_DIR/bin/pip" install -r "$REQ_FILE" --upgrade
    info "依赖更新完成。"
}

# 运行（激活 + 执行）
cmd_run() {
    shift  # 移除 'run' 参数
    if ! [[ -d "$VENV_DIR" ]]; then
        error "虚拟环境不存在，请先运行: ./venv.sh create"
        exit 1
    fi
    source "$VENV_DIR/bin/activate"
    exec python3 "$@"
}

# 清理（删除虚拟环境）
cmd_clean() {
    if [[ -d "$VENV_DIR" ]]; then
        rm -rf "$VENV_DIR"
        info "虚拟环境已删除: $VENV_DIR"
    else
        info "虚拟环境不存在，无需清理。"
    fi
}

# 打印使用说明
usage() {
    cat << EOF
用法: ./venv.sh <命令>

命令:
  create      创建虚拟环境并安装依赖
  install     仅安装依赖（虚拟环境已存在时）
  update      根据 requirements.txt 更新依赖
  clean       删除虚拟环境
  run <cmd>   在虚拟环境中执行命令
              示例: ./venv.sh run python -c "print('hello')"
              示例: ./venv.sh run python engine_cli.py --help

快速开始:
  1. ./venv.sh create   # 首次运行，创建虚拟环境 + 安装依赖
  2. ./venv.sh run python engine_cli.py run-all    # 执行全部规则
  3. ./venv.sh run python engine_cli.py state      # 查看采集状态

激活虚拟环境（手动）:
  source .venv/bin/activate
  deactivate  # 退出虚拟环境
EOF
}

# 主入口
COMMAND="${1:-}"

case "$COMMAND" in
    create)  cmd_create ;;
    install) cmd_install ;;
    update)  cmd_update ;;
    clean)   cmd_clean ;;
    run)
        shift
        cmd_run "$@"
        ;;
    help|--help|-h)
        usage
        ;;
    "")
        # 无参数时显示状态
        if [[ -d "$VENV_DIR" ]]; then
            PIP_VERSION=$("$VENV_DIR/bin/pip" --version 2>/dev/null | awk '{print $2}')
            PYTHON_VERSION=$("$VENV_DIR/bin/python" --version 2>&1)
            info "虚拟环境已就绪: $VENV_DIR"
            info "Python: $PYTHON_VERSION"
            info "pip: $PIP_VERSION"
            echo
            info "运行示例:"
            echo "  ./venv.sh run python -c 'print(1+1)'"
            echo "  ./venv.sh run python engine_cli.py run-all"
        else
            info "虚拟环境未创建。"
            echo "  ./venv.sh create   # 创建虚拟环境"
        fi
        ;;
    *)
        error "未知命令: $COMMAND"
        usage
        exit 1
        ;;
esac
