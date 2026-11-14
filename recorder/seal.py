"""Encrypt recorded order-book files so they can sit in a public repo's artifacts.

Hybrid scheme using only the `openssl` CLI (preinstalled on GitHub runners, macOS,
most Linux, and Git for Windows):
  1. a fresh random AES-256 key + IV per file,
  2. the file encrypted with AES-256-CBC (`openssl enc -K -iv`, no password KDF),
  3. the key+IV encrypted to the operator's RSA public key with OAEP.

Only the matching private key (kept offline by the operator, never in GitHub)
can decrypt. See tools/unseal.sh for the reverse.

Usage: python -m recorder.seal --pubkey keys/recorder_public.pem --src out --dest upload
"""

import argparse
import glob
import os
import secrets
import shutil
import subprocess
import sys

PLACEHOLDER_MARKER = "REPLACE_WITH_OPERATOR_PUBLIC_KEY"


def check_pubkey(pubkey):
    if not os.path.exists(pubkey):
        raise SystemExit(f"public key not found: {pubkey}")
    text = open(pubkey).read()
    if PLACEHOLDER_MARKER in text or "BEGIN PUBLIC KEY" not in text:
        raise SystemExit(f"{pubkey} is not a real public key yet; see docs/PLAN.md")
    if "PRIVATE KEY" in text:
        raise SystemExit(f"{pubkey} contains a PRIVATE key; remove it from the repo immediately")


def seal_file(path, pubkey, dest_dir):
    """Write <name>.enc and <name>.key.enc into dest_dir. Returns their paths."""
    key, iv = secrets.token_bytes(32), secrets.token_bytes(16)
    name = os.path.basename(path)
    enc_path = os.path.join(dest_dir, name + ".enc")
    keyenc_path = os.path.join(dest_dir, name + ".key.enc")
    subprocess.run(["openssl", "enc", "-aes-256-cbc", "-K", key.hex(), "-iv", iv.hex(),
                    "-in", path, "-out", enc_path], check=True)
    subprocess.run(["openssl", "pkeyutl", "-encrypt", "-pubin", "-inkey", pubkey,
                    "-pkeyopt", "rsa_padding_mode:oaep", "-out", keyenc_path],
                   input=(key.hex() + "\n" + iv.hex() + "\n").encode(), check=True)
    return enc_path, keyenc_path


def seal_dir(src, dest, pubkey):
    """Encrypt every books-*.jsonl.gz in src; copy run-*.json (public stats) as-is."""
    check_pubkey(pubkey)
    os.makedirs(dest, exist_ok=True)
    books = sorted(glob.glob(os.path.join(src, "books-*.jsonl.gz")))
    out = []
    for b in books:
        out.extend(seal_file(b, pubkey, dest))
    for r in sorted(glob.glob(os.path.join(src, "run-*.json"))):
        shutil.copy(r, dest)
        out.append(os.path.join(dest, os.path.basename(r)))
    # Guard: nothing readable except run stats may be in dest.
    for f in os.listdir(dest):
        if not (f.endswith(".enc") or (f.startswith("run-") and f.endswith(".json"))):
            raise SystemExit(f"refusing: unexpected unencrypted file in upload dir: {f}")
    return books, out


def main(argv=None):
    p = argparse.ArgumentParser(description="Encrypt recorded books for upload")
    p.add_argument("--pubkey", default="keys/recorder_public.pem")
    p.add_argument("--src", default="out")
    p.add_argument("--dest", default="upload")
    a = p.parse_args(argv)
    books, out = seal_dir(a.src, a.dest, a.pubkey)
    print(f"sealed {len(books)} books file(s) -> {len(out)} file(s) in {a.dest}")
    return 0 if books else 1


if __name__ == "__main__":
    sys.exit(main())
