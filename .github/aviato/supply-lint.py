# aviato:managed profile=python-library version=2.0.1
# aviato:hash=07ae55f17b13eca77bd51e4b7ab5f39e985c978c006d4402b181292e4af6a6d1
# aviato:inputs=fc765bd1af8b69911f2d2f19fa83781590b443d64723218e325418c024d742fc
#!/usr/bin/env python3
r"""Bounded supply-chain lint over a consumer's workflows (Aviato §11.3, Phase 3 decision 2).

MANAGED FILE — Aviato materializes this under `.github/aviato/` and re-renders it
every sync; do not hand-edit. It is the self-contained replacement for the former
`pip install …aviato && aviato lint-actions .` invocation in the reusable
common-lint job, so a flattened consumer CI can run the fail-closed fetch-execute
+ pip exact-version checks WITHOUT installing the Aviato package (Phase 3 decisions
1 & 2). It lives under `.github/aviato/` (never `.github/workflows/`), so it is
never scanned by itself.

COVERAGE DELTA vs `aviato lint-actions` (documented, not silently dropped): this is
a BOUNDED TEXTUAL heuristic over `run:` blocks. It covers the engine's shell-invoked
tool checks — fetch-execute, non-exact `pip install` pins, AND non-exact `npx <pkg>`
invocations (the same `_unpinned_npx_invocations` semantics: a bare `npx tool` or
`npx tool@^1` is flagged; `npx tool@1.2.3`, `npx -p tool@1.2.3`, and
`npx --no-install` pass).

The fetch-execute check here is `bounded_fetch_execute_violations` — deliberately
NOT named after, and NOT equivalent to, the engine's bashlex-AST
`fetch_execute_violations`. Each block is first DEDENTED (the YAML block scalar's
common indent is structure, not shell input), stripped of comments, stripped of
heredoc bodies that are only written as text (see below), and then has its backslash
line continuations folded exactly as a shell folds them — the backslash-newline is
removed outright, becoming neither a space nor the next line's indentation, so a
pipeline split over any number of lines is one command and a continuation splitting a
word (`| bas\` + `h`) rejoins into the real word.

On that text it recognises two shapes: a `curl`/`wget` piped into an interpreter (the
pipe may sit at either end of a line break, and shells whose name merely ends in `sh`
count), and a fetch whose downloaded file a later command in the same block executes.
The download's name comes from `-o`/`--output`/`--output-document`, from a `>` redirect,
or — for `curl -O`/`--remote-name` and a bare `wget` — from the URL's basename, matching
the engine's `_fetch_output_files`. It counts as executed when it is handed to an
interpreter (`bash i.sh`), run directly as the command word (`chmod +x i.sh; ./i.sh`),
or reached through a command PREFIX that introduces the real target rather than being it
(`sudo`, `source`, `.`, `exec`, `eval`, `command`, `builtin`, `env`, `time`, `timeout`,
`nohup`, `setsid`, `stdbuf`, `nice`, `ionice`, `xargs`, and the shell keywords) together
with that prefix's own operands (`env FOO=1 ./i.sh`, `timeout 30 ./i.sh`).
Interpreter names match case-insensitively; the FETCH tool does
not, matching the engine (`CURL` is not curl on a case-sensitive OS, so `CURL … | BASH`
is clean on BOTH sides — parity, not a blind spot). Any checksum/signature verifier in
the block clears it.

HEREDOC BODIES ARE TEXT, NOT COMMANDS, and are dropped before the fetch-execute scan:
`cat <<EOF > README.md` documenting a `curl … | bash` install line is a README, and
flagging it would fail a consumer's own merge-blocking gate with no way to proceed.
Quoted, unquoted, `<<-` indented, and arbitrary delimiters all count; the heredoc's own
command line is never dropped, and a heredoc ends only on a line that IS the delimiter
(`<<-` strips leading TABS only), exactly as a shell ends one. Three carve-outs keep
this fail-closed: a body fed to an interpreter (`bash <<EOF`, `python3 <<'PY'`) is kept,
a body written to a file the same block then RUNS (`cat <<'EOF' > run.sh` …
`bash run.sh`, `tee run.sh <<EOF` …) is kept, and an operator whose delimiter never
reappears — a `<<EOF` that was really text inside a quoted string, or a terminator with
stray trailing whitespace — swallows nothing. (The pip and npx checks still see heredoc
bodies, because the ENGINE's own line-oriented pip/npx scans do too.)

NOT covered (the engine catches these; an honest mistake does not look like them):
command/process substitution (`bash <(curl …)`, `bash -c "$(curl …)"`,
`bash <<<"$(cat i.sh)"`), dynamic command words, and wrapper-resolved programs. The
engine is also strictly BROADER in two ways this bounded check deliberately does not
follow, because doing so textually would misfire on legitimate workflows: it treats a
fetch piped into anything outside a pure-data-sink ALLOWLIST as execution
(`curl … | tar -x`, and so also a word split by a continuation into `bas h`), and it
flags a downloaded file merely REFERENCED by a later command, not just executed
(`curl -o x.json …; jq . x.json`). In exactly two places this check is instead STRICTER
than the engine, in both cases on genuinely executing code the engine misses: a
continuation splitting the FETCH word (`cur\` + `l … | bash` — bashlex folds
continuations to a space, so the engine never reconstructs `curl`), and a quoted
heredoc writing documentation, which makes bashlex fail to parse and the engine fail
CLOSED on a block that executes nothing.

Action/image `uses:` pinning is covered by the zizmor step that runs alongside this
one; the engine's seeded-requirements / pyproject-extra scans do not apply to a
consumer's live workflows. `aviato validate` runs this exact script against a battery
of cases (pip, npx, and each fetch-execute shape above, plus their clean duals) and
fails if it drifts from the engine's intent.

Usage: `python .github/aviato/supply-lint.py [WORKFLOWS_DIR]` (default `.github/workflows`).
Exit 0 = clean (or no workflows), 1 = one or more §11.3 violations reported.
"""

from __future__ import annotations

import re
import shlex
import sys
from pathlib import Path

# Interpreter program names. `(?<![\w.-])` rather than a leading `\b` so `zsh`/`dash`/`ksh` are
# reachable (a `\b` before `sh` can never match inside `zsh`) while `publish`/`mybash` are not; a
# path-qualified `/bin/bash` still matches because `/` is not excluded. Matched CASE-INSENSITIVELY:
# the engine flags a fetch piped into ANY word that is not a known pure data sink, so `curl | BASH`
# is an engine violation and the bounded script has to agree. The FETCH tool stays case-SENSITIVE,
# also for parity — `CURL` is not the curl program on a case-sensitive OS, and the engine's own
# fetch pre-filter does not match it either.
_INTERPRETER = (
    r"(?<![\w.-])(?i:sh|bash|zsh|ksh|dash|ash|fish|csh|tcsh|python[0-9.]*|ruby|perl|node|nodejs|php|pwsh)\b"
)
# A backslash at end of line is a shell LINE CONTINUATION: the next line is part of the same command.
# Folding these before any matching is what stops `curl … \` + `| bash` (a real, executing pipeline)
# from reading as two innocuous lines — the bypass that a pipe-anchored regex alone cannot close,
# whether the continuation sits before the pipe, inside the URL, or repeats several times.
# The shell REMOVES the backslash-newline outright — it does not become a space, and it does not
# consume the next line's indentation — so the fold substitutes the EMPTY string and keeps whatever
# whitespace follows. A continuation splitting a word with NO indentation after it (`| bas\` + `h`)
# therefore rejoins into the real `bash` word, while `bash\` + `  i.sh` still reads as two words.
# Getting this right requires the block to be DEDENTED first (see `_dedent`): inside a YAML block
# scalar the common indent is structure, not shell input.
_CONTINUATION_RE = re.compile(r"\\[ \t]*\r?\n")
# A curl/wget whose output is piped into a shell interpreter — fetch-and-execute. After continuation
# folding the pipeline is usually one line; the pipe may still be the last token of a line
# (`curl … |\n  bash`) or lead the following line, so exactly one newline may sit on either side of
# it. Flagged unless the same block also verifies a checksum/signature.
_FETCH_PIPE_RE = re.compile(
    r"\b(?:curl|wget)\b[^\n|]*(?:\r?\n[ \t]*)?\|[ \t]*(?:\r?\n[ \t]*)?[^\n]*?" + _INTERPRETER
)
_FETCH_TOOL_RE = re.compile(r"\b(?:curl|wget)\b")
_VERIFIER_RE = re.compile(r"\b(?:sha256sum|sha512sum|sha1sum|md5sum|shasum|gpg|cosign|minisign)\b")
# Download-then-run without a pipe (`curl -o f …` then `bash f`): the fetch writes a file that a
# later interpreter command in the same block executes. Mirrors the engine's rule (C) in
# plugins/actionpins, bounded to a textual filename match rather than a shell AST.
_FETCH_OUTFILE_RE = re.compile(r"(?:^|\s)(?:-o|-O|--output|--output-document)[=\s]+(?P<file>[^\s;|&<>]+)")
_FETCH_REDIRECT_RE = re.compile(r">\s*(?P<file>[^\s;|&<>]+)")
# Words that INTRODUCE a command rather than being the program themselves: privilege wrappers, the
# shell's own `source`/`.`/`exec`/`eval`/`command` builtins, and the common exec wrappers. Without
# stripping these, `source ./i.sh` reads as a run of the program `source` and the downloaded
# `./i.sh` is never compared — the engine flags every one of these (its rule (C) matches the
# downloaded name anywhere among a command's words), so rule (C) here has to look past the prefix.
# Shell keywords that introduce a command (`if`, `while`, …) are in the same list for the same reason.
# A leading `\` (quoting the word to bypass an alias) does not change which program runs.
_PREFIX_WORD = (
    r"(?:\\?(?:sudo|doas|source|\.|exec|eval|command|builtin|env|time|timeout|nohup|setsid|stdbuf|"
    r"nice|ionice|xargs|if|elif|while|until|then|do|else|!))"
)
# A prefix word may carry its OWN operands before the real program (`env FOO=bar …`, `timeout 30 …`,
# `nice -n 5 …`), so flags/numbers/assignments are skipped only once a prefix word has been seen —
# skipping them unconditionally would make the command word of ANY command its first argument, which
# would silently widen rule (C) into the engine's much broader "merely referenced" rule.
_PREFIX_OPERAND = r"(?:-[^\s;|&]*|[0-9]+[smhd]?|[A-Za-z_][A-Za-z0-9_]*=[^\s;|&]*)"
_CMD_PREFIX = (
    rf"(?:[A-Za-z_][A-Za-z0-9_]*=[^\s;|&]*[ \t]+)*(?:{_PREFIX_WORD}[ \t]+(?:{_PREFIX_OPERAND}[ \t]+)*)*"
)
# Start-of-command anchor: line start, or just past a `;`/`&`/`|`/`(`/`{` separator or a `then`/`do`
# keyword. ZERO-WIDTH on purpose — a consuming anchor swallows the separator that introduces the NEXT
# command, so `if true; then ./f; fi` would only ever be scanned as `then` and `fi` and the real
# command word in the middle would never be looked at.
_CMD_START = r"(?:^|(?<=[;&|({])|(?<=\bthen)|(?<=\bdo))[ \t]*" + _CMD_PREFIX
_INTERPRETER_CMD_RE = re.compile(_CMD_START + _INTERPRETER + r"(?P<args>[^\n;|&]*)", re.MULTILINE)
# The COMMAND WORD of any command in the block. `curl -o f …; chmod +x f; ./f` executes the download
# with no interpreter word to key on, so rule (C) also compares the program being run against the
# downloaded filenames — the same thing the engine does when it matches its `used` words.
_COMMAND_WORD_RE = re.compile(_CMD_START + r"(?P<cmd>[^\s;|&<>()]+)", re.MULTILINE)

# A `pip install` (bare or `python -m pip install`) argument tail.
_PIP_INSTALL_RE = re.compile(r"\bpip[0-9]*\s+install\b(?P<rest>[^\n]*)")
_PYTHON_PIP_RE = re.compile(r"\bpython[0-9.]*\s+-m\s+pip\s+install\b(?P<rest>[^\n]*)")
# The package-name shape (optionally with an extras spec) after stripping any version specifier.
_PIP_PKG_RE = re.compile(r"^[A-Za-z][A-Za-z0-9._-]*(?:\[[A-Za-z0-9_,.-]+\])?$")
_VERSION_OP_RE = re.compile(r"(===|==|>=|<=|~=|!=|<|>)")
# A VCS requirement exposes no index version; its ref MUST be an immutable full commit SHA.
_VCS_URL_RE = re.compile(r"^git\+[A-Za-z0-9+.-]+://")
_VCS_FULL_SHA_RE = re.compile(r"@[0-9a-f]{40}$")

_RUN_LINE_RE = re.compile(r"^(?P<indent>\s*)-?\s*run\s*:\s*(?P<rest>.*)$")
_SCALAR_RE = re.compile(r"^[|>][+-]?[0-9]*$")

# §11.3 (npx): a tool run via `npx <pkg>` fetches an UNPINNED registry package unless the package
# spec is pinned to an exact SemVer (`pkg@1.2.3`) or the invocation is `npx --no-install` (which
# fails instead of fetching). Mirrors plugins/actionpins._unpinned_npx_invocations semantics.
_NPX_RE = re.compile(r"(?<![\w-])npx(?![\w-])")
_NPM_EXACT_VERSION_RE = re.compile(r"^\d+\.\d+\.\d+(?:[-+][0-9A-Za-z.-]+)?$")


def run_blocks(text: str) -> list[str]:
    """Extract shell `run:` block bodies (tolerant line extractor, no YAML dependency).

    Handles `run: |`/`>` block scalars (dedent-terminated) and inline `run: cmd`, and drops a
    trailing `# comment` on the `run:` key line. Templated bodies (`{{ … }}`) are handled fine
    because this never parses the YAML structurally.
    """
    lines = text.splitlines()
    blocks: list[str] = []
    i = 0
    while i < len(lines):
        match = _RUN_LINE_RE.match(lines[i])
        if not match:
            i += 1
            continue
        rest = re.sub(r"\s+#.*$", "", match.group("rest")).strip()
        if _SCALAR_RE.match(rest):
            base = len(match.group("indent"))
            body: list[str] = []
            i += 1
            while i < len(lines):
                line = lines[i]
                if line.strip() and (len(line) - len(line.lstrip())) <= base:
                    break
                body.append(line)
                i += 1
            blocks.append("\n".join(body))
        else:
            blocks.append(rest)
            i += 1
    return blocks


def _dedent(block: str) -> str:
    """Remove the block scalar's common indentation — it is YAML structure, not shell input.

    Only the COMMON prefix goes; a line's own relative indentation is real shell whitespace and is
    what makes `bash\\` + `  i.sh` two words while `| bas\\` + `h` is one. Without this the file's
    key indentation would make every continued line look indented.
    """
    indents = [len(line) - len(line.lstrip()) for line in block.splitlines() if line.strip()]
    base = min(indents) if indents else 0
    return "\n".join(line[base:] if line.strip() else line for line in block.splitlines())


# A heredoc operator (`<<EOF`, `<<'EOF'`, `<<-EOF`, `<<"delim"`, `<<\EOF`). `(?<!<)` keeps a
# HERESTRING (`<<<"$(curl …)"`) out — that operand is a shell word, not a body of lines.
_HEREDOC_RE = re.compile(r"(?<!<)<<(?P<dash>-?)\s*['\"\\]?(?P<delim>[A-Za-z_][A-Za-z0-9_.-]*)")
# Where a heredoc's own command line puts the body. A `>` redirect covers `cat <<EOF > install.sh`,
# but `tee install.sh <<EOF` names the file as a plain operand, so every non-flag word after the
# command word counts as a candidate target — over-detecting one only costs a body being kept.
_HEREDOC_REDIRECT_RE = re.compile(r">>?\s*(?P<file>[^\s;|&<>]+)")
_HEREDOC_OPERATOR_RE = re.compile(r"<<-?\s*['\"\\]?[A-Za-z_][A-Za-z0-9_.-]*['\"]?")
_WORD_RE = re.compile(r"[^\s;|&<>()'\"]+")


def _heredoc_targets(line: str) -> set[str]:
    """Files the heredoc body on this command line could land in."""
    targets = {_normalise_path(m.group("file")) for m in _HEREDOC_REDIRECT_RE.finditer(line)}
    words = _WORD_RE.findall(_HEREDOC_OPERATOR_RE.sub(" ", line))
    # Skip the command word itself: `cat` is not where the body goes, and treating it as a target
    # would make a second `cat` elsewhere in the block resurrect an unrelated documentation body.
    targets |= {_normalise_path(word) for word in words[1:] if not word.startswith("-")}
    return targets


def _strip_heredoc_bodies(text: str) -> str:
    """Drop heredoc BODIES that are only written as text, keeping every command line.

    A heredoc body is data, not commands: `cat <<EOF > README.md` documenting a `curl … | bash`
    install line is a README, not an execution, and flagging it would fail a consumer's own
    merge-blocking gate with no way out. The engine's AST walk never sees a heredoc body either.

    Three fail-closed carve-outs keep this from becoming a hiding place. The body is KEPT when the
    heredoc's own command line names an interpreter (`bash <<EOF`, `python3 <<'PY'`) — that body IS
    executed; when the body is written to a file the same block later RUNS (`cat <<'EOF' > run.sh`
    … `bash run.sh`); and when the delimiter never appears again, so an operator that was really
    just text inside a quoted string (`echo "<<EOF"`) cannot swallow the rest of the block. The
    heredoc's command line itself is never dropped, so a fetch-execute written on it is still seen.
    """
    lines = text.splitlines()
    kept: list[str] = []
    deferred: list[tuple[set[str], list[str]]] = []  # (write targets, body) pending the execution check
    i = 0
    while i < len(lines):
        line = lines[i]
        kept.append(line)
        i += 1
        keep_body = bool(re.search(_INTERPRETER, line))
        targets = _heredoc_targets(line)
        for match in _HEREDOC_RE.finditer(line):
            if line.count("'", 0, match.start()) % 2 or line.count('"', 0, match.start()) % 2:
                continue  # the operator sits inside a quoted string — not a heredoc
            delim = match.group("delim")
            # A heredoc ends only on a line that IS the delimiter — trailing whitespace or extra
            # indentation does not terminate it in a shell (`<<-` strips leading TABS only), and a
            # near-miss leaves the heredoc unterminated, which the loop below then fails closed on.
            tab_stripped = bool(match.group("dash"))
            body: list[str] = []
            while i < len(lines) and (lines[i].lstrip("\t") if tab_stripped else lines[i]) != delim:
                body.append(lines[i])
                i += 1
            if i >= len(lines):  # unterminated: not a heredoc after all — keep the text, fail closed
                kept.extend(body)
                break
            terminator = lines[i]
            i += 1
            if keep_body:
                kept.extend(body)
            else:
                deferred.append((targets, body))
            kept.append(terminator)  # inert either way
    if deferred:
        executed = _executed_words("\n".join(kept))
        for targets, body in deferred:
            if targets & executed:
                kept.extend(body)
    return "\n".join(kept)


def _executed_words(text: str) -> set[str]:
    """Normalised filenames this text runs — as a command word, or as an interpreter's operand."""
    words = {_normalise_path(m.group("cmd")) for m in _COMMAND_WORD_RE.finditer(text)}
    for match in _INTERPRETER_CMD_RE.finditer(text):
        words |= {_normalise_path(token) for token in match.group("args").split()}
    return words


def _decomment(block: str) -> str:
    """Drop whole-line `#` comments so a check never fires on documentation text."""
    return "\n".join(line for line in block.splitlines() if not line.lstrip().startswith("#"))


def _remote_basenames(line: str) -> list[str]:
    """Basenames a fetch writes when the FILENAME COMES FROM THE URL, not from a flag.

    `curl -O URL` and a bare `wget URL` both save to the URL's basename, so a `curl -O …/i.sh`
    followed by `bash i.sh` is the same download-then-run as the `-o` form. Mirrors the engine's
    `_fetch_output_files` remote-name handling.
    """
    urls = [word.strip("'\"") for word in _WORD_RE.findall(line) if "://" in word]
    if not urls:
        return []
    remote_name = re.search(r"(?:^|\s)(?:-[a-zA-Z]*O[a-zA-Z]*|--remote-name(?:-all)?)(?:\s|$)", line)
    if re.search(r"\bcurl\b", line) and remote_name:
        return [url.split("?", 1)[0].rstrip("/").rsplit("/", 1)[-1] for url in urls]
    if re.search(r"\bwget\b", line) and not re.search(r"(?:^|\s)(?:-[a-zA-Z]*O|--output-document)", line):
        return [url.split("?", 1)[0].rstrip("/").rsplit("/", 1)[-1] for url in urls]
    return []


def _downloaded_filenames(text: str) -> list[str]:
    """Filenames a `curl`/`wget` line in this block writes: `-o`/`--output`, `>`, or the URL basename."""
    names: list[str] = []
    for line in text.splitlines():
        if not _FETCH_TOOL_RE.search(line):
            continue
        for name in _remote_basenames(line):
            if name and name not in names:
                names.append(name)
        for pattern in (_FETCH_OUTFILE_RE, _FETCH_REDIRECT_RE):
            for match in pattern.finditer(line):
                name = match.group("file").strip("'\"")
                if name and name not in ("-", "/dev/null", "/dev/stdout") and name not in names:
                    names.append(name)
    return names


def _normalise_path(name: str) -> str:
    """Strip quotes and a leading `./` so `./install.sh` and `install.sh` compare equal."""
    name = name.strip("'\"")
    return name[2:] if name.startswith("./") else name


def _fetch_then_execute(text: str) -> str | None:
    """A downloaded file that a later command in the same block runs, or None.

    Bounded stand-in for the engine's rule (C) — no dataflow, just "this block downloaded a file
    and this block executes that filename". Two shapes: the file is handed to an interpreter
    (`bash i.sh`), or it is run directly as the command word (`chmod +x i.sh; ./i.sh`). Callers
    apply the block-level verifier exemption first, exactly as the engine does.
    """
    names = {_normalise_path(name) for name in _downloaded_filenames(text)}
    if not names:
        return None
    for match in _INTERPRETER_CMD_RE.finditer(text):
        if _FETCH_TOOL_RE.search(match.group(0)):
            continue  # the fetch line itself, not a later consumer
        if names & {_normalise_path(token) for token in match.group("args").split()}:
            return match.group(0).strip()[:80]
    for match in _COMMAND_WORD_RE.finditer(text):
        if _normalise_path(match.group("cmd")) in names:
            return match.group(0).strip()[:80]
    return None


def bounded_fetch_execute_violations(block: str) -> list[str]:
    """Bounded fetch-execute check — deliberately NOT the engine's `fetch_execute_violations`.

    Covers the two shapes an honest mistake takes: a `curl … | <interpreter>` pipeline (including
    one continued across a line break), and a `curl -o f …` whose file a later command in the same
    block executes. Any checksum/signature verifier in the block clears it (block-level, as in the
    engine). The engine's bashlex AST walk over substitutions, redirects and wrappers is out of
    scope here — see the COVERAGE DELTA note in the module docstring.
    """
    # Dedent (YAML structure) → drop comments → drop written-only heredoc bodies → fold line
    # continuations. The order matters: comments must go before heredoc scanning so a commented-out
    # `<<EOF` cannot swallow live lines, and continuations fold last so a body that was never shell
    # in the first place never gets joined onto a command line.
    text = _CONTINUATION_RE.sub("", _strip_heredoc_bodies(_decomment(_dedent(block))))
    if not _FETCH_TOOL_RE.search(text):
        return []
    if _VERIFIER_RE.search(text):
        return []
    match = _FETCH_PIPE_RE.search(text)
    if match:
        return [f"fetch-and-execute without a verified checksum: {match.group(0).strip()[:80]}"]
    excerpt = _fetch_then_execute(text)
    if excerpt:
        return [f"fetch-and-execute without a verified checksum: {excerpt}"]
    return []


def _pip_tokens(rest: str) -> list[str]:
    """Split a `pip install` argument tail into tokens, collapsing PEP 440 operator whitespace."""
    rest = re.sub(r"\s*(===|==|>=|<=|~=|!=|<|>)\s*", r"\1", rest)
    import shlex

    try:
        return shlex.split(rest, comments=False, posix=True)
    except ValueError:
        return rest.split()


def _unpinned_pip_packages(rest: str) -> list[str]:
    """PyPI package tokens in a `pip install` arg tail NOT pinned to an exact version.

    §11.3 requires an exact `name==X.Y.Z`. A bare name or a non-exact specifier is flagged;
    local installs (`.`/`-e path`/paths), requirement/constraint files, wheels, URLs, and
    shell-variable tokens are exempt. A `git+…` VCS requirement is flagged unless its ref is a
    full 40-hex commit SHA (or a shell-variable ref resolved at runtime).
    """
    tokens = _pip_tokens(rest)
    flagged: list[str] = []
    skip_next = False
    for token in tokens:
        if skip_next:
            skip_next = False
            continue
        stripped = token.strip("'\"")
        if stripped in ("-r", "--requirement", "-c", "--constraint"):
            skip_next = True
            continue
        if stripped.startswith("-"):
            continue
        spec = stripped.split(";", 1)[0].strip().strip("'\"")
        if "'" in spec or '"' in spec:
            continue
        if _VCS_URL_RE.match(spec):
            if not (_VCS_FULL_SHA_RE.search(spec) or spec.endswith("}")):
                flagged.append(spec)
            continue
        if not spec or spec.startswith((".", "/", "${", "$(", "http", "file")) or "/" in spec:
            continue
        if spec.endswith(".whl"):
            continue
        name = _VERSION_OP_RE.split(spec, 1)[0]
        if not _PIP_PKG_RE.match(name):
            continue
        if "==" in spec and "*" not in spec.split("==", 1)[1]:
            continue
        flagged.append(spec)
    return flagged


def pip_violations(block: str) -> list[str]:
    text = _decomment(block)
    seen: list[str] = []
    for pattern in (_PIP_INSTALL_RE, _PYTHON_PIP_RE):
        for match in pattern.finditer(text):
            for pkg in _unpinned_pip_packages(match.group("rest")):
                seen.append(f"pip install without an exact version pin: {pkg}")
    return seen


def _npm_package_exact_versioned(spec: str) -> bool:
    """Whether an npm package spec names one exact SemVer package version."""
    spec = spec.strip("'\"")
    if "$" in spec or ":" in spec or ("/" not in spec and spec.startswith(".")):
        return False
    at_index = spec.rfind("@")
    if at_index <= 0:
        # Scoped packages start with `@`, so their version separator must be a later `@`.
        return False
    version = spec[at_index + 1 :]
    if any(marker in version for marker in ("*", "^", "~", "<", ">", "=")):
        return False
    return bool(_NPM_EXACT_VERSION_RE.match(version))


def _shlex_split(line: str) -> list[str]:
    try:
        return shlex.split(line, posix=True)
    except ValueError:
        return line.split()


def _npx_invocation_is_pinned(command: str) -> bool:
    """A single `npx …` command is pinned iff `--no-install`, or its resolved package spec is exact."""
    tokens = _shlex_split(command)
    if not tokens or tokens[0] != "npx":
        return True
    args = tokens[1:]
    if "--no-install" in args:
        return True
    package_specs: list[str] = []
    first_command_token: str | None = None
    skip_next = False
    for index, arg in enumerate(args):
        if skip_next:
            skip_next = False
            continue
        if arg in ("-p", "--package"):
            if index + 1 < len(args):
                package_specs.append(args[index + 1])
                skip_next = True
            continue
        if arg.startswith("--package=") or arg.startswith("-p="):
            package_specs.append(arg.split("=", 1)[1])
            continue
        if arg == "--":
            continue
        if arg.startswith("-"):
            continue
        first_command_token = arg
        break
    if package_specs:
        return all(_npm_package_exact_versioned(spec) for spec in package_specs)
    return first_command_token is not None and _npm_package_exact_versioned(first_command_token)


def npx_violations(block: str) -> list[str]:
    """Bounded npx check: each `npx <pkg>` whose package spec is not pinned to an exact version."""
    violations: list[str] = []
    for raw_line in _decomment(block).splitlines():
        line = raw_line.strip()
        if not line:
            continue
        command_line = raw_line.split("#", 1)[0]
        match = _NPX_RE.search(command_line)
        if match is None:
            continue
        command = command_line[match.start() :].strip()
        if not _npx_invocation_is_pinned(command):
            violations.append(f"npx may fetch an unpinned registry tool: {command}")
    return violations


def scan_text(text: str) -> list[str]:
    violations: list[str] = []
    for block in run_blocks(text):
        violations.extend(bounded_fetch_execute_violations(block))
        violations.extend(pip_violations(block))
        violations.extend(npx_violations(block))
    # de-dup while preserving order
    out: list[str] = []
    for item in violations:
        if item not in out:
            out.append(item)
    return out


def scan_dir(workflows_dir: Path) -> list[str]:
    violations: list[str] = []
    files = sorted(p for ext in ("*.yml", "*.yaml") for p in workflows_dir.glob(ext))
    for path in files:
        text = path.read_text(encoding="utf-8", errors="replace")
        for violation in scan_text(text):
            violations.append(f"{path.name}: {violation}")
    return violations


def main(argv: list[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    workflows_dir = Path(args[0]) if args else Path(".github/workflows")
    if not workflows_dir.is_dir():
        print("No workflows to check.")
        return 0
    violations = scan_dir(workflows_dir)
    if violations:
        print("::error::supply-chain pin violations (§11.3):")
        for violation in violations:
            print(f"::error::{violation}")
        return 1
    print("Fetch-execute + pip exact-pin checks OK.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
