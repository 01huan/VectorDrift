#!/bin/sh
# ============================================================================
#  Vector Drift - one-click launcher for macOS
#
#  macOS opens .sh files in a text editor, so this wrapper runs the real
#  launcher (run.sh) in Terminal.  Keep it in the same folder as run.sh.
#
#  The terminal stays open with the reason when something fails.
# ============================================================================
SCRIPT_DIR=$(CDPATH= cd "$(dirname "$0")" && pwd -P)
exec sh "$SCRIPT_DIR/run.sh" "$@"
