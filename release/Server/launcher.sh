#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
BOLD='\033[1m'
NC='\033[0m'

show_status() {
  if [ -f server.pid ] && kill -0 "$(cat server.pid)" 2>/dev/null; then
    echo -e "  狀態：${GREEN}執行中${NC} (PID $(cat server.pid))"
  else
    echo -e "  狀態：${YELLOW}未啟動${NC}"
  fi
}

show_menu() {
  clear
  echo ""
  echo -e "${BOLD}╔══════════════════════════════════════════╗${NC}"
  echo -e "${BOLD}║     Evidence-First Server 控制面板       ║${NC}"
  echo -e "${BOLD}╠══════════════════════════════════════════╣${NC}"
  echo -e "${BOLD}║                                          ║${NC}"
  show_status
  echo -e "${BOLD}║                                          ║${NC}"
  echo -e "  ${CYAN}1${NC}  首次安裝（建立 venv、安裝依賴）"
  echo -e "  ${CYAN}2${NC}  啟動 Server"
  echo -e "  ${CYAN}3${NC}  停止 Server"
  echo -e "  ${CYAN}4${NC}  查看狀態"
  echo -e "  ${CYAN}0${NC}  離開"
  echo -e "${BOLD}║                                          ║${NC}"
  echo -e "${BOLD}╚══════════════════════════════════════════╝${NC}"
  echo ""
}

do_install() {
  echo ""
  echo -e "${CYAN}正在安裝 Server 環境...${NC}"
  PAUSE_ON_EXIT=0 bash ./scripts/install.sh --no-pause
  echo ""
  echo -e "${GREEN}安裝完成！${NC}"
  read -r -p "按 Enter 返回選單..."
}

do_start() {
  echo ""
  if [ -f server.pid ] && kill -0 "$(cat server.pid)" 2>/dev/null; then
    echo -e "${YELLOW}Server 已在執行中${NC}"
    read -r -p "按 Enter 返回選單..."
    return
  fi
  echo -e "${CYAN}正在啟動 Server...${NC}"
  PAUSE_ON_EXIT=0 bash ./scripts/start.sh --no-pause
  echo ""
  echo -e "${GREEN}Server 已啟動${NC}"
  read -r -p "按 Enter 返回選單..."
}

do_stop() {
  echo ""
  if [ ! -f server.pid ] || ! kill -0 "$(cat server.pid)" 2>/dev/null; then
    echo -e "${YELLOW}Server 未在執行${NC}"
    read -r -p "按 Enter 返回選單..."
    return
  fi
  kill "$(cat server.pid)" 2>/dev/null
  rm -f server.pid
  echo -e "${GREEN}Server 已停止${NC}"
  read -r -p "按 Enter 返回選單..."
}

while true; do
  show_menu
  read -r -p "請選擇 [0-4]: " choice
  case "$choice" in
    1) do_install ;;
    2) do_start ;;
    3) do_stop ;;
    4) show_status; read -r -p "按 Enter 返回選單..." ;;
    0|q|Q) echo "再見！"; exit 0 ;;
    *) echo -e "${RED}無效的選擇${NC}"; sleep 1 ;;
  esac
done
