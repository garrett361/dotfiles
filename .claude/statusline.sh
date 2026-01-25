#!/bin/bash

input=$(cat)

MODEL=$(echo "$input" | jq -r '.model.display_name // "Unknown"')
PERCENT_USED=$(echo "$input" | jq -r '.context_window.used_percentage // 0')
TOTAL_COST=$(echo "$input" | jq -r '.cost.total // 0')
INPUT_TOKENS=$(echo "$input" | jq -r '.context_window.total_input_tokens // 0')
OUTPUT_TOKENS=$(echo "$input" | jq -r '.context_window.total_output_tokens // 0')

INPUT_K=$(awk "BEGIN {printf \"%.1fk\", $INPUT_TOKENS/1000}")
OUTPUT_K=$(awk "BEGIN {printf \"%.1fk\", $OUTPUT_TOKENS/1000}")

printf "[%s] Ctx: %.1f%% | In: %s Out: %s | Cost: \$%.3f" \
    "$MODEL" "$PERCENT_USED" "$INPUT_K" "$OUTPUT_K" "$TOTAL_COST"
