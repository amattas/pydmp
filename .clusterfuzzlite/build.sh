#!/bin/bash -eu
# Builds every fuzz/fuzz_*.py atheris target and its seed corpus into $OUT.
# --copy-metadata: pydmp resolves __version__ from package metadata at import time,
# which PyInstaller bundles leave out unless asked.

python3 -m pip install --no-cache-dir .

for fuzzer in fuzz/fuzz_*.py; do
  name=$(basename -s .py "$fuzzer")
  compile_python_fuzzer "$fuzzer" --copy-metadata pydmp
  (cd "fuzz/corpus/$name" && zip -q -r "$OUT/${name}_seed_corpus.zip" .)
done
