#!/usr/bin/env bash
# Decrypt files produced by recorder/seal.py. Run on YOUR computer, where the private key lives.
# Usage: tools/unseal.sh path/to/recorder_private.pem DIR_OR_FILES...
#   For each X.enc with a matching X.key.enc, writes X (e.g. books-....jsonl.gz) next to it.
set -euo pipefail
priv="$1"; shift
files=()
for a in "$@"; do
  if [ -d "$a" ]; then while IFS= read -r f; do files+=("$f"); done < <(find "$a" -name '*.jsonl.gz.enc'); else files+=("$a"); fi
done
for enc in "${files[@]}"; do
  base="${enc%.enc}"
  keyfile="$base.key.enc"
  [ -f "$keyfile" ] || { echo "missing $keyfile" >&2; exit 1; }
  { read -r k; read -r iv; } < <(openssl pkeyutl -decrypt -inkey "$priv" -pkeyopt rsa_padding_mode:oaep -in "$keyfile")
  openssl enc -d -aes-256-cbc -K "$k" -iv "$iv" -in "$enc" -out "$base"
  echo "decrypted $base"
done
