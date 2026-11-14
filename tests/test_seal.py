"""Round-trip test for recorder/seal.py + tools/unseal.sh using a throwaway key (needs openssl)."""

import gzip
import os
import shutil
import subprocess
import tempfile
import unittest

from recorder import seal

HAVE_OPENSSL = shutil.which("openssl") is not None
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


@unittest.skipUnless(HAVE_OPENSSL, "openssl not installed")
class SealTests(unittest.TestCase):
    def setUp(self):
        self.d = tempfile.mkdtemp()
        self.priv = os.path.join(self.d, "priv.pem")
        self.pub = os.path.join(self.d, "pub.pem")
        subprocess.run(["openssl", "genpkey", "-algorithm", "RSA", "-pkeyopt", "rsa_keygen_bits:2048",
                        "-out", self.priv], check=True, capture_output=True)
        subprocess.run(["openssl", "pkey", "-in", self.priv, "-pubout", "-out", self.pub], check=True)
        self.src = os.path.join(self.d, "out")
        os.makedirs(self.src)
        self.payload = b'{"slug":"a","bids":[["0.4","10"]]}\n' * 50
        with gzip.open(os.path.join(self.src, "books-R.jsonl.gz"), "wb") as f:
            f.write(self.payload)
        with open(os.path.join(self.src, "run-R.json"), "w") as f:
            f.write('{"books_written": 50}')

    def tearDown(self):
        shutil.rmtree(self.d)

    def test_round_trip(self):
        dest = os.path.join(self.d, "upload")
        books, out = seal.seal_dir(self.src, dest, self.pub)
        self.assertEqual(sorted(os.listdir(dest)), ["books-R.jsonl.gz.enc", "books-R.jsonl.gz.key.enc", "run-R.json"])
        enc = open(os.path.join(dest, "books-R.jsonl.gz.enc"), "rb").read()
        self.assertNotIn(b"slug", enc)
        subprocess.run([os.path.join(ROOT, "tools", "unseal.sh"), self.priv, dest], check=True, capture_output=True)
        with gzip.open(os.path.join(dest, "books-R.jsonl.gz")) as f:
            self.assertEqual(f.read(), self.payload)

    def test_refuses_placeholder_and_private_keys(self):
        with self.assertRaises(SystemExit):
            ph = os.path.join(self.d, "placeholder.pem")
            open(ph, "w").write(seal.PLACEHOLDER_MARKER + "\n")
            seal.check_pubkey(ph)
        with self.assertRaises(SystemExit):
            seal.check_pubkey(self.priv)

    def test_refuses_stray_plaintext_in_upload(self):
        dest = os.path.join(self.d, "upload")
        os.makedirs(dest)
        open(os.path.join(dest, "books-old.jsonl.gz"), "w").close()
        with self.assertRaises(SystemExit):
            seal.seal_dir(self.src, dest, self.pub)


if __name__ == "__main__":
    unittest.main()


class RepoKeyTests(unittest.TestCase):
    def test_repo_key_is_public_only(self):
        text = open(os.path.join(ROOT, "keys", "recorder_public.pem")).read()
        self.assertNotIn("PRIVATE KEY", text)
