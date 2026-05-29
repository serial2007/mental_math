#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")"

JAVA_HOME="${JAVA_HOME:-/usr/lib/jvm/java-17-openjdk}"
if [[ ! -x "$JAVA_HOME/bin/java" ]]; then
  echo "JDK 17 not found at $JAVA_HOME" >&2
  echo "On Arch Linux, install it with: sudo pacman -S jdk17-openjdk" >&2
  exit 1
fi

export JAVA_HOME
export PATH="$JAVA_HOME/bin:$PATH"

.venv-android/bin/buildozer android debug
