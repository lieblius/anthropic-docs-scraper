init:
    uv run scraper.py --init
update:
    uv run scraper.py --update
setup-command:
    ./setup-command.sh
check:
    uvx ruff check --fix --unsafe-fixes
format:
    uvx ruff format
codeql: check format
