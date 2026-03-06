#!/bin/bash
# Claude Code statusline — pure bash, no external dependencies.
INPUT=$(cat)

# Extract JSON values with grep (simple flat patterns from known schema)
extract() { echo "$INPUT" | grep -o "\"$1\":[^,}]*" | head -1 | sed 's/.*":\s*//;s/^"//;s/"$//'; }

MODEL=$(extract "display_name")
COST=$(extract "total_cost_usd")
PCT=$(extract "used_percentage")

# Defaults (guard against empty AND literal "null")
MODEL=${MODEL:-?}; [ "$MODEL" = "null" ] && MODEL="?"
PCT=${PCT:-0}; [ "$PCT" = "null" ] && PCT=0
COST=${COST:-0}; [ "$COST" = "null" ] && COST=0
COST=$(printf '%.2f' "$COST" 2>/dev/null || echo "0.00")

# Git branch
BRANCH=$(git rev-parse --abbrev-ref HEAD 2>/dev/null)

# ANSI colors
RST='\033[0m'; DIM='\033[2m'; GRN='\033[32m'; YLW='\033[33m'; RED='\033[31m'; CYN='\033[36m'; MAG='\033[35m'

# Context color threshold (red at autocompact level, yellow at 50%)
COMPACT=${CLAUDE_AUTOCOMPACT_PCT_OVERRIDE:-80}
WARN=50
CC=$GRN; [ "$PCT" -ge "$WARN" ] 2>/dev/null && CC=$YLW; [ "$PCT" -ge "$COMPACT" ] 2>/dev/null && CC=$RED

# Progress bar: filled + dim empty (10 chars)
W=10; F=$((PCT * W / 100)); E=$((W - F))
CBAR="${CC}"
for ((i=0; i<F; i++)); do CBAR+="█"; done
CBAR+="${DIM}"
for ((i=0; i<E; i++)); do CBAR+="░"; done
CBAR+="${RST}"

# Context compaction hint
HINT=""
if [ "$PCT" -ge "$COMPACT" ]; then
    HINT=" ${DIM}|${RST} ${RED}Run \`/compact\` now${RST}"
elif [ "$PCT" -ge "$WARN" ]; then
    HINT=" ${DIM}|${RST} ${YLW}Consider \`/compact\`${RST}"
fi

# Assemble
LINE="${CYN}${MODEL}${RST} ${DIM}|${RST} \$${COST} ${DIM}|${RST} ${CBAR} ${CC}${PCT}%${RST}${HINT}"
[ -n "$BRANCH" ] && LINE+=" ${DIM}|${RST} ${MAG}⎇ ${BRANCH}${RST}"

printf "%b\n" "$LINE"
