#!/usr/bin/env bash
set -euo pipefail

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
TOOLS_DIR="$PROJECT_ROOT/.tools"
TARGET="${1:-all}"

install_boss() {
  if ! command -v uv >/dev/null 2>&1; then
    echo "未找到 uv。请先按 https://docs.astral.sh/uv/getting-started/installation/ 安装 uv。" >&2
    exit 1
  fi

  local boss_bin="$TOOLS_DIR/bin/boss"
  local installed_version=""
  if [[ -x "$boss_bin" ]]; then
    installed_version="$("$boss_bin" --version 2>/dev/null || true)"
  fi
  if [[ "$installed_version" != *"2.0.0"* ]]; then
    mkdir -p "$TOOLS_DIR/uv" "$TOOLS_DIR/bin"
    UV_TOOL_DIR="$TOOLS_DIR/uv" UV_TOOL_BIN_DIR="$TOOLS_DIR/bin" \
      uv tool install --force "boss-agent-cli==2.0.0"
  else
    echo "BOSS CLI 已安装：$installed_version"
  fi

  if [[ ! -x "$boss_bin" ]]; then
    echo "BOSS CLI 安装后未在预期位置找到：$boss_bin" >&2
    exit 1
  fi
}

install_job_pro() {
  if ! command -v node >/dev/null 2>&1 || ! command -v npm >/dev/null 2>&1; then
    echo "安装 job-pro 需要 Node.js >= 18 和 npm。" >&2
    exit 1
  fi
  local node_major
  node_major="$(node -p 'Number(process.versions.node.split(".")[0])')"
  if (( node_major < 18 )); then
    echo "当前 Node.js 主版本为 $node_major；job-pro 需要 Node.js >= 18。" >&2
    exit 1
  fi

  local job_pro_prefix="$TOOLS_DIR/job-pro"
  npm install --prefix "$job_pro_prefix" --no-save --no-audit --no-fund \
    "@ha7ch/job-pro@1.2.1"
  if [[ ! -x "$job_pro_prefix/node_modules/.bin/job-pro" ]]; then
    echo "job-pro 安装后未在预期位置找到可执行文件。" >&2
    exit 1
  fi
}

case "$TARGET" in
  all)
    install_boss
    install_job_pro
    ;;
  boss)
    install_boss
    ;;
  job-pro)
    install_job_pro
    ;;
  *)
    echo "用法：bash scripts/install_provider_tools.sh [all|boss|job-pro]" >&2
    exit 2
    ;;
esac

echo "Provider CLI 安装检查完成。对应配置："
if [[ "$TARGET" == "all" || "$TARGET" == "boss" ]]; then
  echo "  BOSS_CLI_COMMAND=./.tools/bin/boss"
fi
if [[ "$TARGET" == "all" || "$TARGET" == "job-pro" ]]; then
  echo "  JOB_PRO_COMMAND=./.tools/job-pro/node_modules/.bin/job-pro"
fi
