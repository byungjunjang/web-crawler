#!/bin/sh
# node 경로를 찾아 같은 폴더의 스크립트를 실행한다. GUI로 띄운 앱은 nvm PATH가 없을 수 있다. 못 찾으면 실패를 드러낸다(조용히 삼키지 않는다).
dir=$(cd "$(dirname "$0")" && pwd)
script="$1"
shift
n=$(command -v node 2>/dev/null)
if [ -z "$n" ]; then
  for c in "$HOME"/.nvm/versions/node/*/bin/node /opt/homebrew/bin/node /usr/local/bin/node; do
    [ -x "$c" ] && n="$c"
  done
fi
if [ -z "$n" ]; then
  printf '%s\n' "[plan] node를 찾지 못해 계획 하네스($script)가 실행되지 않았다. AGENTS.md 캡슐과 .plan/CAPSULE.md를 직접 읽고, 이 실패를 사용자에게 먼저 알려라."
  exit 0
fi
case "$script" in
  /*) ;;
  *) script="$dir/$script" ;;
esac
exec "$n" "$script" "$@"
