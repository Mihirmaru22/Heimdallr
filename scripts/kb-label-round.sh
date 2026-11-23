#!/usr/bin/env bash
# One labelling round on the server, so each round is one command instead of many.
#   export N  : update the code, export N pages (70% from PDL Technology companies) to ~/claude_pages.csv
#   train FILE...: import Claude's label files, train the classifier, label every homepage,
#                  and write a 200-page sample to ~/label_sample.csv for checking
set -euo pipefail
export PATH="$HOME/.local/bin:$PATH"  # uv, when run over ssh without a login shell
cd ~/Heimdallr-kb
git fetch -q origin claude/project-thread-zjy7wi && git checkout -q --detach FETCH_HEAD
cd backend && uv sync -q
cli() { uv run python -m app.cli "$@"; }
case "${1:-}" in
  export)
    cli kb-teach --model claude --export-pages "${2:-1000}" --tech-share 0.7 --out ~/claude_pages.csv ;;
  train)
    shift
    for f in "$@"; do cli kb-teach --model claude --import "$f"; done
    cli kb-train --teacher claude
    cli kb-classify --again
    cli kb-classify --export-sample 200 --out ~/label_sample.csv ;;
  *) echo "usage: $0 export N | train FILE..."; exit 1 ;;
esac
