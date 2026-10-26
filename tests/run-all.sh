#!/bin/bash
# Unit tests for every script, the structure check, and the end-to-end example.
set -u
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
FAIL=0
TOTAL=0
FILES=0
for t in "$ROOT"/swap-*/scripts/test_*.py; do
  out="$(cd "$(dirname "$t")" && python3 -I "$(basename "$t")" 2>&1)"; rc=$?
  n="$(printf '%s\n' "$out" | sed -n 's/^Ran \([0-9]*\) tests.*/\1/p')"
  TOTAL=$((TOTAL + ${n:-0}))
  FILES=$((FILES + 1))
  if [ $rc -ne 0 ]; then echo "FAIL $t"; printf '%s\n' "$out" | tail -15; FAIL=1
  elif [ "${n:-0}" -lt 1 ]; then echo "FAIL $t ran zero tests (an empty or broken test file is not a pass)"; FAIL=1
  else echo "ok   $(basename "$t") (${n} tests)"; fi
done
echo "unit tests run: $TOTAL in $FILES test files"
[ "$FILES" -ge 12 ] || { echo "FAIL expected at least 12 script test files, found $FILES"; FAIL=1; }
python3 -I "$ROOT/tests/check.py" "$ROOT" 1 || FAIL=1
OUT="$(mktemp)"
python3 -I "$ROOT/example/run_example.py" --skills-dir "$ROOT" > "$OUT" 2>&1 && echo "example chain: PASS" || { echo "example chain: FAIL"; tail -20 "$OUT"; FAIL=1; }
rm -f "$OUT"
[ $FAIL -eq 0 ] && echo "ALL PASS" || { echo "FAILURES ABOVE"; exit 1; }
