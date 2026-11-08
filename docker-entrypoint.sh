#!/bin/sh
set -eu

# Named Docker volumes are commonly mounted as root-owned directories.
# Prepare the persistent data directory before dropping application privileges.
mkdir -p /data
chown -R aios:aios /data
exec gosu aios "$@"
