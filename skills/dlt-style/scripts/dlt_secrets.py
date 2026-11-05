#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.12"
# dependencies = ["tomlkit>=0.13.2"]
# ///
"""Show, add, move and remove dlt secrets without printing a secret value.

Run it from the project root, the folder the pipelines run from, because dlt
reads `.dlt` from the working directory.

`show` prints each secrets file dlt 1.32.0 reads for the project: the
project's `.dlt/secrets.toml` and the global `secrets.toml` in dlt's global
folder, `~/.dlt` by default. A `<...>` placeholder prints verbatim and every
other value prints as `***`. It then lists the environment variable that each
key maps to, as set or unset, never its value, and ends with the keys dlt would
still read as a placeholder.

`add` deep-merges a TOML fragment of placeholders into `.dlt/secrets.toml`,
creating the file when it is missing. It never overwrites a key, refuses any
value that is not a placeholder, keeps comments and order, and prints the
redacted result.

`move` moves one value of `.dlt/secrets.toml` to another key, with the comment
after it, and refuses when the value is missing or a table, or the new key
exists. `remove` deletes one key, or a whole table with the comments inside it,
and refuses a key that is not there. Both drop each table they leave with no
key and no comment, keep every other value and comment, write the file only
when it reads back as intended, and print the redacted result.
"""

import argparse
import json
import os
import re
import sys
import tempfile
from collections.abc import Mapping, MutableMapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Final

import tomlkit
import tomllib
from tomlkit.container import Container
from tomlkit.exceptions import ParseError, TOMLKitError
from tomlkit.items import AoT, Comment, InlineTable, Item, Table
from tomlkit.toml_document import TOMLDocument

type KeyPath = tuple[str, ...]

CONFIG_FOLDER_DEFAULT: Final = ".dlt"
"""dlt's settings folder, unless `DLT_CONFIG_FOLDER` names another."""

SECRETS_FILE: Final = "secrets.toml"
"""The file name dlt reads secrets from, in the project and in the global folder."""

GLOBAL_DIR_ROOT: Final = Path("/var/dlt")
"""dlt's global folder when the process runs as root."""

GLOBAL_DIR_FALLBACK: Final = "dlt"
"""The folder name dlt uses under `XDG_DATA_HOME` or the temp folder."""

FILL_MARKER: Final = "# fill this in!"
"""The comment `dlt init` writes after each sample value."""

DLT_INIT_SAMPLES: Final = (0, 1.0, "1.0", "1768-07-21", "1768-07-21T02:56:07.000003Z")
"""The samples `dlt init` writes for an integer, float, decimal, date and timestamp."""

PLACEHOLDER: Final = re.compile(r"<[^\r\n]+>")
"""A one-line string that starts with `<` and ends with `>`."""

BARE_KEY: Final = re.compile(r"[A-Za-z0-9_-]+")
"""A TOML key that needs no quotes."""

KEY_PART: Final = r"""[A-Za-z0-9_-]+|"(?:[^"\\\r\n]|\\.)*"|'[^'\r\n]*'"""
"""One key of a dotted path: bare, in double quotes or in single quotes."""

DOTTED_PATH: Final = re.compile(
    rf"[ \t]*(?:{KEY_PART})(?:[ \t]*\.[ \t]*(?:{KEY_PART}))*[ \t]*",
)
"""A TOML dotted key, such as `sources.github.access_token` or `sources."a.b".key`."""

DLT_VARIABLE: Final = re.compile(r"(?:^|__)(?:SOURCES|DESTINATION|CREDENTIALS)__")
"""An environment variable under one of dlt's credential sections."""

REDACTED: Final = "***"
"""What prints in place of every value that is not a placeholder."""

TABLES_MAX: Final = 10_000
"""The most tables one document may hold, so every walk is bounded."""

NEW_FILE_MODE: Final = 0o600
"""Owner read and write only, for a secrets file this script creates."""

PERMISSION_BITS: Final = 0o777
"""The mask that keeps a file's permission bits from `st_mode`."""


@dataclass(frozen=True, slots=True)
class Leaf:
    """One value in a TOML document, at its full key path."""

    path: KeyPath
    """The keys from the document root to the value."""

    value: object
    """The value as tomlkit parsed it."""

    marked: bool
    """Whether the value carries the `# fill this in!` comment of `dlt init`."""


@dataclass(frozen=True, slots=True)
class MergeReport:
    """The outcome of merging a fragment into a secrets file."""

    added: tuple[Leaf, ...]
    """The placeholders written, in fragment order."""

    kept: tuple[KeyPath, ...]
    """The keys left alone because the file already sets them."""

    blocked: tuple[KeyPath, ...]
    """The keys left alone because a parent key holds a value, not a table."""


class SecretsError(Exception):
    """A file, fragment or path the command refuses; the message never holds a value."""


def main(argv: Sequence[str] | None = None) -> int:
    """Run the command line.

    Parameters
    ----------
    argv
        The arguments after the script name. None reads `sys.argv`.

    Returns
    -------
    :
        The exit status: 0 on success, 1 when a file, fragment or path is refused.

    """
    arguments = parse_arguments(argv)
    project_file = project_secrets_path(os.environ, Path.cwd())
    try:
        if arguments.command == "show":
            text = show(project_file, global_secrets_path(os.environ), os.environ)
        elif arguments.command == "add":
            text = add(project_file, read_fragments(arguments.fragments))
        elif arguments.command == "move":
            text = move(project_file, arguments.source, arguments.target)
        else:
            text = remove(project_file, arguments.path)
    except SecretsError as error:
        sys.stderr.write(f"error: {error}\n")
        return 1
    sys.stdout.write(text)
    return 0


def parse_arguments(argv: Sequence[str] | None) -> argparse.Namespace:
    """Parse the command and its arguments.

    Parameters
    ----------
    argv
        The arguments after the script name. None reads `sys.argv`.

    Returns
    -------
    :
        The namespace, with `command` set to `show`, `add`, `move` or `remove`.

    """
    parser = argparse.ArgumentParser(
        description="Show, add, move and remove dlt secrets without printing a "
        "secret value.",
    )
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser(
        "show",
        help="print each secrets file redacted, and each key's env var as set or unset",
    )
    add_parser = commands.add_parser(
        "add",
        help="merge a TOML fragment of <...> placeholders into .dlt/secrets.toml",
    )
    add_parser.add_argument(
        "fragments",
        nargs="*",
        metavar="FRAGMENT",
        help="a TOML fragment, such as 'sources.github.access_token = \"<token>\"'; "
        "with none, the fragment is read from standard input",
    )
    move_parser = commands.add_parser(
        "move",
        help="move one value of .dlt/secrets.toml to another key, without printing it",
    )
    move_parser.add_argument(
        "source",
        metavar="FROM",
        help="the dotted key path of the value, such as sources.shop.credentials.token",
    )
    move_parser.add_argument(
        "target",
        metavar="TO",
        help="the dotted key path to move it to, such as sources.shop.token",
    )
    remove_parser = commands.add_parser(
        "remove",
        help="delete one key or a whole table of .dlt/secrets.toml",
    )
    remove_parser.add_argument(
        "path",
        metavar="PATH",
        help="the dotted key path of the key or table, such as "
        "sources.filesystem.credentials",
    )
    return parser.parse_args(argv)


def show(project_file: Path, global_file: Path, environ: Mapping[str, str]) -> str:
    """Render both secrets files redacted, then the environment variable of each key.

    Parameters
    ----------
    project_file
        The project's secrets file.
    global_file
        The secrets file in dlt's global folder.
    environ
        The environment, read for which variables are set.

    Returns
    -------
    :
        The report, ending with the placeholders dlt would still read.

    Raises
    ------
    SecretsError
        When a secrets file is not valid TOML.

    """
    sections = [
        "dlt takes each key from an environment variable first, "
        "then the project file, then the global file.",
    ]
    found_by_file: list[list[Leaf]] = []
    for label, path in (("project", project_file), ("global", global_file)):
        document = read_document(path)
        if document is None:
            sections.append(f"{label} file: {path} (not found)")
        else:
            found = leaves(document)
            found_by_file.append(found)
            sections.append("\n".join([f"{label} file: {path}", *render(found)]))
    found_all = [leaf for found in found_by_file for leaf in found]
    variables = env_lines(found_all, environ)
    sections.append("\n".join(["environment variables:", *variables]))
    left = placeholders_left(found_by_file, environ)
    sections.append("\n".join([f"placeholders left: {len(left)}", *left]))
    return "\n\n".join(sections) + "\n"


def add(project_file: Path, texts: Sequence[str]) -> str:
    """Merge fragments of placeholders into the project's secrets file.

    Parameters
    ----------
    project_file
        The project's secrets file, created when it is missing.
    texts
        The TOML fragments, merged in order.

    Returns
    -------
    :
        The report of added and kept keys, then the file, redacted.

    Raises
    ------
    SecretsError
        When a fragment or the file is not valid TOML, the file is not UTF-8,
        a fragment holds a value that is not a placeholder, or the merged file
        would not read back.

    """
    found = fragment_leaves(texts)
    original = read_text(project_file) or ""
    document = parse_toml(with_final_newline(original), str(project_file))
    report = merge(document, found)
    lines = [f"added: {dotted(leaf.path)}" for leaf in report.added]
    lines.extend(f"kept: {dotted(path)} (already set)" for path in report.kept)
    lines.extend(
        f"kept: {dotted(path)} (a parent key holds a value)" for path in report.blocked
    )
    if report.added:
        merged = tomlkit.dumps(document).rstrip("\n") + "\n"
        check_round_trip(original, merged, report.added)
        write_atomically(project_file, merged)
        lines.append(f"wrote: {project_file}")
    else:
        lines.append(f"unchanged: {project_file}")
    lines.extend(["", f"project file: {project_file}", *render(leaves(document))])
    return "\n".join(lines) + "\n"


def move(project_file: Path, source_text: str, target_text: str) -> str:
    """Move one value of the project's secrets file to another key.

    Parameters
    ----------
    project_file
        The project's secrets file.
    source_text
        The dotted key path of the value, such as `sources.shop.credentials.token`.
    target_text
        The dotted key path to move it to, such as `sources.shop.token`.

    Returns
    -------
    :
        The move, then the file, redacted.

    Raises
    ------
    SecretsError
        When a path is not a dotted key path, the value is missing or is a
        table, the new key exists or sits under a value, an inline table would
        drop the value's comment, or the file would not read back as before
        with the value moved.

    """
    source = parse_path(source_text, "the path to move from")
    target = parse_path(target_text, "the path to move to")
    original = with_final_newline(read_text(project_file) or "")
    document = parse_toml(original, str(project_file))
    holder = holder_of(document, source, project_file)
    value = item_of(holder, source[-1])
    if isinstance(value, Mapping | AoT):
        msg = f"refused, nothing written: {dotted(source)} is a table, not one value"
        raise SecretsError(msg)
    table, created = parent_table(document, target[:-1])
    if table is None:
        msg = f"refused, nothing written: a key above {dotted(target)} holds a value"
        raise SecretsError(msg)
    if target[-1] in table:
        msg = f"refused, nothing written: {dotted(target)} already exists"
        raise SecretsError(msg)
    if not isinstance(table, InlineTable):
        value = as_line(value)
    elif isinstance(value, Item) and value.trivia.comment:
        msg = (
            "refused, nothing written: an inline table would drop the comment "
            f"after {dotted(source)}"
        )
        raise SecretsError(msg)
    table[target[-1]] = value
    del holder[source[-1]]
    pruned = prune(document, source[:-1])
    if (
        isinstance(table, Table)
        and (created or pruned)
        and not table.as_string().endswith("\n\n")
    ):
        table.add(tomlkit.nl())
    expected = values_of(original, "the file")
    expected[target] = expected.pop(source, None)
    done = f"moved: {dotted(source)} -> {dotted(target)}"
    return write_change(project_file, document, expected, done)


def remove(project_file: Path, path_text: str) -> str:
    """Delete one key, or a whole table, from the project's secrets file.

    Parameters
    ----------
    project_file
        The project's secrets file.
    path_text
        The dotted key path of the key or table, such as
        `sources.filesystem.credentials`.

    Returns
    -------
    :
        The removal, then the file, redacted.

    Raises
    ------
    SecretsError
        When the path is not a dotted key path or not in the file, or the file
        would not read back as before without the key.

    """
    path = parse_path(path_text, "the path to remove")
    original = with_final_newline(read_text(project_file) or "")
    document = parse_toml(original, str(project_file))
    holder = holder_of(document, path, project_file)
    del holder[path[-1]]
    prune(document, path[:-1])
    expected = {
        key: value
        for key, value in values_of(original, "the file").items()
        if key[: len(path)] != path
    }
    return write_change(project_file, document, expected, f"removed: {dotted(path)}")


def read_fragments(fragments: Sequence[str]) -> list[str]:
    """Return the fragments given as arguments, or the one on standard input.

    Parameters
    ----------
    fragments
        The fragments given as arguments, possibly none.

    Returns
    -------
    :
        At least one fragment text.

    Raises
    ------
    SecretsError
        When no fragment is given and standard input is a terminal.

    """
    if fragments:
        texts = list(fragments)
    elif sys.stdin.isatty():
        msg = "give the fragment as an argument or on standard input"
        raise SecretsError(msg)
    else:
        texts = [sys.stdin.read()]
    return texts


def project_secrets_path(environ: Mapping[str, str], cwd: Path) -> Path:
    """Return the project's secrets file, where dlt 1.32.0's `RunContext` looks.

    Parameters
    ----------
    environ
        The environment, read for `DLT_PROJECT_DIR` and `DLT_CONFIG_FOLDER`.
    cwd
        The working directory, the project root unless `DLT_PROJECT_DIR` names another.

    Returns
    -------
    :
        The absolute path of the file, whether or not it exists.

    """
    run_dir = cwd / environ.get("DLT_PROJECT_DIR", ".")
    return run_dir / config_folder(environ) / SECRETS_FILE


def global_secrets_path(environ: Mapping[str, str]) -> Path:
    """Return the global secrets file, as dlt 1.32.0's `global_dir()` finds it.

    `DLT_DATA_DIR` moves the pipelines' working folders, not this file.

    Parameters
    ----------
    environ
        The environment, read for `XDG_DATA_HOME` and `DLT_CONFIG_FOLDER`.

    Returns
    -------
    :
        The path of the file, whether or not it exists.

    """
    folder = config_folder(environ)
    if sys.platform != "win32" and os.geteuid() == 0:
        return GLOBAL_DIR_ROOT / SECRETS_FILE
    try:
        home = Path.home()
    except RuntimeError:
        return Path(tempfile.gettempdir()) / GLOBAL_DIR_FALLBACK / SECRETS_FILE
    if not (home.is_dir() and os.access(home, os.W_OK)):
        return Path(tempfile.gettempdir()) / GLOBAL_DIR_FALLBACK / SECRETS_FILE
    xdg_data_home = environ.get("XDG_DATA_HOME")
    if xdg_data_home is None or (home / folder).is_dir():
        return home / folder / SECRETS_FILE
    return Path(xdg_data_home) / GLOBAL_DIR_FALLBACK / SECRETS_FILE


def config_folder(environ: Mapping[str, str]) -> str:
    """Return the name of dlt's settings folder.

    Parameters
    ----------
    environ
        The environment, read for `DLT_CONFIG_FOLDER`.

    Returns
    -------
    :
        The folder name, `.dlt` by default.

    """
    return environ.get("DLT_CONFIG_FOLDER", CONFIG_FOLDER_DEFAULT)


def read_document(path: Path) -> TOMLDocument | None:
    """Parse a TOML file.

    Parameters
    ----------
    path
        The file to read.

    Returns
    -------
    :
        The document, or None when the file does not exist.

    Raises
    ------
    SecretsError
        When the file is not UTF-8 or not valid TOML.

    """
    text = read_text(path)
    if text is None:
        return None
    return parse_toml(text, str(path))


def read_text(path: Path) -> str | None:
    """Read a file as UTF-8 text.

    Parameters
    ----------
    path
        The file to read.

    Returns
    -------
    :
        The text, or None when the file does not exist.

    Raises
    ------
    SecretsError
        When the file is not UTF-8. The message never holds its bytes.

    """
    try:
        return path.read_text(encoding="utf-8")
    except FileNotFoundError:
        return None
    except UnicodeDecodeError:
        msg = f"{path} is not UTF-8 text"
        raise SecretsError(msg) from None


def parse_toml(text: str, label: str) -> TOMLDocument:
    """Parse TOML text, reporting an error by position only.

    Parameters
    ----------
    text
        The TOML text.
    label
        The name of the text in an error message: a file path or `fragment 1`.

    Returns
    -------
    :
        The document, with comments and order kept.

    Raises
    ------
    SecretsError
        When the text is not valid TOML. The message gives the line and column,
        never the text, because the text may hold a secret.

    """
    try:
        return tomlkit.parse(text)
    except ParseError as error:
        msg = f"{label} is not valid TOML (line {error.line}, column {error.col})"
        raise SecretsError(msg) from None
    except TOMLKitError:
        msg = f"{label} is not valid TOML (a key or table is defined twice)"
        raise SecretsError(msg) from None


def leaves(document: Mapping[str, Any]) -> list[Leaf]:
    """Flatten a document into its values, table by table, in document order.

    Parameters
    ----------
    document
        A parsed TOML document or table. Inline tables count as tables, and
        arrays count as values.

    Returns
    -------
    :
        Each value with its full key path. A table's own values come before its
        subtables, so a table's values sit together.

    Raises
    ------
    SecretsError
        When the document holds more than `TABLES_MAX` tables.

    """
    found: list[Leaf] = []
    stack: list[tuple[KeyPath, Mapping[str, Any]]] = [((), document)]
    for _ in range(TABLES_MAX):
        if not stack:
            return found
        path, table = stack.pop()
        subtables: list[tuple[KeyPath, Mapping[str, Any]]] = []
        for key, value in table.items():
            if isinstance(value, Mapping):
                subtables.append(((*path, str(key)), value))
            else:
                found.append(Leaf((*path, str(key)), value, marked=is_marked(value)))
        stack.extend(reversed(subtables))
    msg = f"the document holds more than {TABLES_MAX} tables"
    raise SecretsError(msg)


def is_marked(value: object) -> bool:
    """Tell whether a value carries the `# fill this in!` comment of `dlt init`.

    Parameters
    ----------
    value
        A parsed value. Only tomlkit items carry comments.

    Returns
    -------
    :
        True when the comment after the value is the marker.

    """
    if isinstance(value, Item):
        return value.trivia.comment.strip() == FILL_MARKER
    return False


def is_placeholder(value: object) -> bool:
    """Tell whether a value is a placeholder, a one-line string written as `<...>`.

    Parameters
    ----------
    value
        A parsed value.

    Returns
    -------
    :
        True for a placeholder.

    """
    if isinstance(value, str):
        return PLACEHOLDER.fullmatch(value) is not None
    return False


def render(found: Sequence[Leaf]) -> list[str]:
    """Render values as TOML lines, a placeholder verbatim and any other value as `***`.

    Parameters
    ----------
    found
        Values in the order `leaves` returns them.

    Returns
    -------
    :
        The lines, with a table header before each table's values, or one
        `(empty)` line when there are no values.

    """
    lines: list[str] = []
    table: KeyPath = ()
    for leaf in found:
        parent = leaf.path[:-1]
        if parent != table:
            if lines:
                lines.append("")
            lines.append(f"[{dotted(parent)}]")
            table = parent
        lines.append(f"{key_text(leaf.path[-1])} = {value_text(leaf)}")
    return lines or ["(empty)"]


def value_text(leaf: Leaf) -> str:
    """Render one value: a placeholder verbatim, anything else redacted.

    Parameters
    ----------
    leaf
        The value to render.

    Returns
    -------
    :
        The placeholder as a TOML string, or `***`, followed by `dlt init`'s
        marker comment when the value carries it.

    """
    if is_placeholder(leaf.value):
        return json.dumps(str(leaf.value), ensure_ascii=False)
    if leaf.marked:
        return f"{REDACTED}  {FILL_MARKER}"
    return REDACTED


def env_lines(found: Sequence[Leaf], environ: Mapping[str, str]) -> list[str]:
    """List the environment variable of each key as set or unset, never its value.

    Parameters
    ----------
    found
        The values of every secrets file.
    environ
        The environment.

    Returns
    -------
    :
        One line per variable: first each key's variable in file order, then
        each other set variable under `sources`, `destination` or `credentials`,
        marked `(no key in the files)`. An empty variable prints as
        `set (empty)`, because dlt takes the empty string over the files.

    """
    names = list(dict.fromkeys(env_name(leaf.path) for leaf in found))
    others = sorted(set(filter(DLT_VARIABLE.search, environ)) - set(names))
    if not names and not others:
        return ["(no keys in the files, and no dlt source or destination variable set)"]
    width = max(len(name) for name in (*names, *others))
    lines = [f"{name.ljust(width)}  {env_state(environ.get(name))}" for name in names]
    lines.extend(
        f"{name.ljust(width)}  {env_state(environ[name])} (no key in the files)"
        for name in others
    )
    return lines


def env_state(value: str | None) -> str:
    """Describe a variable as set, set but empty, or unset.

    Parameters
    ----------
    value
        The variable's value, or None when it is unset. Only its emptiness is read.

    Returns
    -------
    :
        `unset`, `set (empty)` or `set`.

    """
    if value is None:
        return "unset"
    if value:
        return "set"
    return "set (empty)"


def placeholders_left(
    found_by_file: Sequence[Sequence[Leaf]],
    environ: Mapping[str, str],
) -> list[str]:
    """List the keys dlt would still resolve to a placeholder.

    Parameters
    ----------
    found_by_file
        The values of each secrets file, the project file first.
    environ
        The environment. A key whose variable is set and not empty is filled,
        because the variable wins over the files.

    Returns
    -------
    :
        One indented key path per placeholder left, in file order, with a
        sample value `dlt init` wrote marked as such.

    """
    effective: dict[KeyPath, Leaf] = {}
    for found in found_by_file:
        for leaf in found:
            effective.setdefault(leaf.path, leaf)
    lines: list[str] = []
    for path, leaf in effective.items():
        if environ.get(env_name(path)):
            continue
        if is_placeholder(leaf.value):
            lines.append(f"  {dotted(path)}")
        elif is_init_sample(leaf):
            lines.append(f"  {dotted(path)} (a dlt init sample value)")
    return lines


def is_init_sample(leaf: Leaf) -> bool:
    """Tell whether a value is a sample `dlt init` wrote and nobody has replaced.

    Parameters
    ----------
    leaf
        A value with its marker flag.

    Returns
    -------
    :
        True when the value carries the `# fill this in!` comment and still
        equals the sample `dlt init` writes for its type, or the key's own
        name for a type it has no sample for. A boolean never counts, because
        tomlkit gives it no comment.

    """
    return leaf.marked and (
        leaf.value in DLT_INIT_SAMPLES or leaf.value == leaf.path[-1]
    )


def env_name(path: KeyPath) -> str:
    """Return the environment variable dlt reads for a key path.

    Parameters
    ----------
    path
        The key path, such as `("sources", "github", "access_token")`.

    Returns
    -------
    :
        The path in capitals joined by `__`, such as `SOURCES__GITHUB__ACCESS_TOKEN`.

    """
    return "__".join(path).upper()


def dotted(path: KeyPath) -> str:
    """Join a key path with dots, quoting each key that is not bare.

    Parameters
    ----------
    path
        The key path.

    Returns
    -------
    :
        The path as TOML writes it, such as `sources.github.access_token`.

    """
    return ".".join(key_text(key) for key in path)


def key_text(key: str) -> str:
    """Render one key as TOML writes it.

    Parameters
    ----------
    key
        The key.

    Returns
    -------
    :
        The key bare when it may be, otherwise quoted.

    """
    if BARE_KEY.fullmatch(key):
        return key
    return json.dumps(key, ensure_ascii=False)


def fragment_leaves(texts: Sequence[str]) -> list[Leaf]:
    """Parse the fragments and check that every value is a placeholder.

    Parameters
    ----------
    texts
        The TOML fragments.

    Returns
    -------
    :
        The placeholders of every fragment, in order.

    Raises
    ------
    SecretsError
        When a fragment is not valid TOML, holds no key, or holds a value that
        is not a placeholder. The message names the keys, never the values.

    """
    found: list[Leaf] = []
    for number, text in enumerate(texts, start=1):
        found.extend(leaves(parse_toml(text, f"fragment {number}")))
    if not found:
        msg = "the fragment holds no key"
        raise SecretsError(msg)
    refused = [dotted(leaf.path) for leaf in found if not is_placeholder(leaf.value)]
    if refused:
        msg = f"refused, nothing written: not a <...> placeholder: {', '.join(refused)}"
        raise SecretsError(msg)
    return found


def merge(document: TOMLDocument, found: Sequence[Leaf]) -> MergeReport:
    """Add each placeholder whose key the document lacks, creating tables as needed.

    Parameters
    ----------
    document
        The secrets file, changed in place.
    found
        The placeholders to add.

    Returns
    -------
    :
        Which keys were added, kept, or blocked by a value at a parent key.
        The values of one table go in together, and a table the merge creates
        ends with a blank line, so the next table stays apart from it.

    """
    groups: dict[KeyPath, list[Leaf]] = {}
    for leaf in found:
        groups.setdefault(leaf.path[:-1], []).append(leaf)
    added: list[Leaf] = []
    kept: list[KeyPath] = []
    blocked: list[KeyPath] = []
    for path, group in groups.items():
        table, created = parent_table(document, path)
        if table is None:
            blocked.extend(leaf.path for leaf in group)
        else:
            for leaf in group:
                if leaf.path[-1] in table:
                    kept.append(leaf.path)
                else:
                    table[leaf.path[-1]] = fresh_item(leaf.value)
                    added.append(leaf)
            if created and isinstance(table, Table):
                table.add(tomlkit.nl())
    return MergeReport(added=tuple(added), kept=tuple(kept), blocked=tuple(blocked))


def fresh_item(value: object) -> Item:
    """Return a placeholder as a new TOML string that keeps its comment.

    A new item ends its line like every other key, wherever the fragment put it.

    Parameters
    ----------
    value
        A placeholder from a fragment.

    Returns
    -------
    :
        The string item, with the fragment's comment after it when there was one.

    """
    item = tomlkit.string(str(value))
    if isinstance(value, Item):
        comment = value.trivia.comment.removeprefix("#").strip()
        if comment:
            item.comment(comment)
    return item


def parent_table(
    document: TOMLDocument,
    path: KeyPath,
) -> tuple[MutableMapping[str, Any] | None, bool]:
    """Return the table at a key path, creating each missing table on the way.

    Parameters
    ----------
    document
        The secrets file, changed in place when a table is missing.
    path
        The key path of the table.

    Returns
    -------
    :
        The table, or None when a key on the path holds a value, not a table,
        and whether the table at the end of the path was created. A table
        created inside an inline table is inline, because TOML allows no other.
        A table that only its subtables declare loses the copy tomlkit gives it
        of their header's comment, which would print twice once it gets a key.

    """
    table: MutableMapping[str, Any] = document
    created = False
    for key in path:
        created = key not in table
        if created:
            inline = isinstance(table, InlineTable)
            table[key] = tomlkit.inline_table() if inline else tomlkit.table()
        child = table[key]
        if isinstance(child, MutableMapping):
            table = child
        else:
            return None, False
    if isinstance(table, Table) and table.is_super_table():
        table.trivia.comment_ws = ""
        table.trivia.comment = ""
    return table, created


def check_round_trip(original: str, merged: str, added: Sequence[Leaf]) -> None:
    """Check that the merged text reads back as the original plus the added keys.

    Parameters
    ----------
    original
        The file's text before the merge, empty for a new file.
    merged
        The text about to be written.
    added
        The placeholders the merge added.

    Raises
    ------
    SecretsError
        When the merged text would not read back as intended, or not as TOML
        1.0, the version `tomllib` reads.

    """
    try:
        expected: dict[str, Any] = tomllib.loads(original)
        written = tomllib.loads(merged)
    except tomllib.TOMLDecodeError:
        msg = "the merged file would not read back as TOML 1.0, so nothing was written"
        raise SecretsError(msg) from None
    for leaf in added:
        table = expected
        for key in leaf.path[:-1]:
            table = table.setdefault(key, {})
        table[leaf.path[-1]] = str(leaf.value)
    if written != expected:
        msg = "the merged file would not read back as written, so nothing was written"
        raise SecretsError(msg)


def with_final_newline(text: str) -> str:
    """Return the text with a final newline, so an appended table starts a line.

    Parameters
    ----------
    text
        The file's text, possibly empty.

    Returns
    -------
    :
        The text, unchanged when it is empty or already ends with a newline.

    """
    if text and not text.endswith("\n"):
        return text + "\n"
    return text


def parse_path(text: str, label: str) -> KeyPath:
    """Parse a dotted key path, written the way `show` and `add` print one.

    Parameters
    ----------
    text
        The path, such as `sources.github.access_token` or `sources."a.b".key`.
    label
        The name of the path in an error message.

    Returns
    -------
    :
        The keys from the document root.

    Raises
    ------
    SecretsError
        When the text is not one TOML dotted key. The message never holds the
        text, because a value given there by mistake may be a secret.

    """
    msg = f"{label} is not a dotted key path, such as sources.github.access_token"
    if DOTTED_PATH.fullmatch(text) is None:
        raise SecretsError(msg)
    try:
        found = leaves(tomlkit.parse(f"{text} = 0"))
    except TOMLKitError:
        raise SecretsError(msg) from None
    if len(found) != 1:
        raise SecretsError(msg)
    return found[0].path


def holder_of(
    document: TOMLDocument,
    path: KeyPath,
    project_file: Path,
) -> MutableMapping[str, Any]:
    """Return the table that holds the last key of a path.

    Parameters
    ----------
    document
        The secrets file.
    path
        The key path.
    project_file
        The file's path, for the error message.

    Returns
    -------
    :
        The table, which holds the key.

    Raises
    ------
    SecretsError
        When the path is not in the file, a key on the way included.

    """
    table: object = document
    for key in path[:-1]:
        table = table.get(key) if isinstance(table, MutableMapping) else None
    if not isinstance(table, MutableMapping) or path[-1] not in table:
        msg = f"refused, nothing written: {dotted(path)} is not in {project_file}"
        raise SecretsError(msg)
    return table


def item_of(holder: MutableMapping[str, Any], key: str) -> object:
    """Return the value at a key as tomlkit's item, so a boolean keeps its comment.

    Parameters
    ----------
    holder
        The table that holds the key.
    key
        The key.

    Returns
    -------
    :
        The item. A table split into pieces across the file gives no item, so a
        boolean there comes back as a plain `bool`, without its comment.

    """
    if isinstance(holder, Container | Table | InlineTable):
        return holder.item(key)
    return holder[key]


def as_line(value: object) -> object:
    """Set a moved item to sit on a line of its own, as a key of a table.

    Parameters
    ----------
    value
        The item, possibly from an inline table or from a last line that has
        no final newline.

    Returns
    -------
    :
        The same item, with no indent and a line break after it.

    """
    if isinstance(value, Item):
        value.trivia.indent = ""
        if "\n" not in value.trivia.trail:
            value.trivia.trail = "\n"
    return value


def prune(document: TOMLDocument, path: KeyPath) -> bool:
    """Delete each table on a path, deepest first, that holds no key and no comment.

    Parameters
    ----------
    document
        The secrets file, changed in place.
    path
        The key path of the table a key was taken from. The walk stops at the
        first table that keeps a key or a comment.

    Returns
    -------
    :
        Whether a table was deleted, taking the blank line after it along.

    """
    chain: list[tuple[MutableMapping[str, Any], str]] = []
    table: MutableMapping[str, Any] = document
    for key in path:
        chain.append((table, key))
        table = table[key]
    pruned = False
    for holder, key in reversed(chain):
        if not is_bare(holder[key]):
            break
        del holder[key]
        pruned = True
    return pruned


def is_bare(value: object) -> bool:
    """Tell whether a value is a table with no key and no comment.

    Parameters
    ----------
    value
        A parsed value.

    Returns
    -------
    :
        True for an empty table or inline table with no comment, on its header
        line or inside it, so deleting it loses nothing.

    """
    if not isinstance(value, Table | InlineTable) or value or value.trivia.comment:
        return False
    return not any(isinstance(item, Comment) for _, item in value.value.body)


def values_of(text: str, label: str) -> dict[KeyPath, object]:
    """Read every value of a TOML text by its key path, as `tomllib` reads it.

    Parameters
    ----------
    text
        The TOML text.
    label
        The name of the text in an error message.

    Returns
    -------
    :
        Each value by its full key path. An empty table holds no value, so it
        does not show.

    Raises
    ------
    SecretsError
        When `tomllib` cannot read the text as TOML 1.0.

    """
    try:
        document = tomllib.loads(text)
    except tomllib.TOMLDecodeError:
        msg = f"{label} would not read as TOML 1.0, so nothing was written"
        raise SecretsError(msg) from None
    return {leaf.path: leaf.value for leaf in leaves(document)}


def write_change(
    project_file: Path,
    document: TOMLDocument,
    expected: Mapping[KeyPath, object],
    done: str,
) -> str:
    """Write a changed secrets file once it reads back with the expected values.

    Parameters
    ----------
    project_file
        The project's secrets file.
    document
        The changed file.
    expected
        Every value the file must hold afterwards, by key path.
    done
        The line that reports the change.

    Returns
    -------
    :
        The change, then the file, redacted.

    Raises
    ------
    SecretsError
        When the changed file would not read back with exactly those values.

    """
    text = tomlkit.dumps(document).strip("\n")
    text = f"{text}\n" if text.strip() else ""
    if values_of(text, "the changed file") != expected:
        msg = "the changed file would not read back as intended, so nothing was written"
        raise SecretsError(msg)
    write_atomically(project_file, text)
    lines = [done, f"wrote: {project_file}", "", f"project file: {project_file}"]
    return "\n".join([*lines, *render(leaves(document))]) + "\n"


def write_atomically(path: Path, text: str) -> None:
    """Replace a file in one step, so a failed write never leaves it half written.

    A new file gets owner-only permissions; an existing file keeps its own.

    Parameters
    ----------
    path
        The file to write. Its folder is created when missing.
    text
        The full new content.

    """
    path.parent.mkdir(parents=True, exist_ok=True)
    mode = path.stat().st_mode & PERMISSION_BITS if path.exists() else NEW_FILE_MODE
    with tempfile.NamedTemporaryFile(
        "w",
        encoding="utf-8",
        newline="",
        dir=path.parent,
        prefix=".secrets-",
        suffix=".tmp",
        delete=False,
    ) as handle:
        handle.write(text)
        temporary = Path(handle.name)
    try:
        temporary.chmod(mode)
        temporary.replace(path)
    except OSError:
        temporary.unlink(missing_ok=True)
        raise


if __name__ == "__main__":
    sys.exit(main())
