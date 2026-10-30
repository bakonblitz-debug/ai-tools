# Observatory

Read-only dashboard over the session and usage TSVs the harness collector writes: eight tiles for sessions, active time, tokens and cost, effort, errors, interruptions, denials and cache use.

    cp .env.example .env    # set METRICS_DIR, DB_DIR, prefixes
    make up
    open http://localhost:3400
    make test

The metrics are mounted read-only; the app keeps a SQLite copy in DB_DIR and reloads it when a TSV changes.
