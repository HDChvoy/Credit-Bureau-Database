#!/usr/bin/env bash
# =====================================================================
# Build the Experian database this application runs against.
#
# Usage:   ./build.sh [database_name]
# Default: experian_credit
#
# These are the Deliverable #2 scripts, copied here so that this folder
# can stand up its own database. Scripts 08 (temp tables), 09
# (demonstrations) and 10 (index benchmark) from D2 are not included:
# they demonstrate objects rather than create them, and the application
# does not depend on them.
#
# Order matters. 04_functions precedes 05_views because several views
# call those functions, and 06_triggers follows 02_load_data because
# trg_inquiry_removal backfills the rows that were loaded before it
# existed.
# =====================================================================
set -u

DB="${1:-experian_credit}"
HERE="$(cd "$(dirname "$0")" && pwd)"

echo "Building $DB ..."
for f in 01_ddl 02_load_data 03_indexes 04_functions 05_views 06_triggers 07_procedures
do
    echo "  -> $f.sql"
    psql -v ON_ERROR_STOP=1 -q -d "$DB" -f "$HERE/$f.sql" \
        || { echo "FAILED on $f.sql"; exit 1; }
done

echo "Done. $DB is ready."
