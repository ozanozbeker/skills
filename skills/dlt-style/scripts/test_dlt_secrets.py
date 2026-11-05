"""Tests for dlt_secrets.py: a positive and a negative case per command and path rule.

Run from the repository root:

uv run --no-project --with pytest --with tomlkit --with "dlt==1.32.0" \
    pytest skills/dlt-style/scripts
"""

import importlib.util
import io
import json
import os
import stat
import subprocess
import sys
from pathlib import Path
from types import ModuleType

import pytest
import tomllib

sys.dont_write_bytecode = True  # keep __pycache__ of the script out of the repository

SCRIPT = Path(__file__).with_name("dlt_secrets.py")

SECRETS = ("SNTL", "86753091", "3.1415", "2024-01-31")
"""Text in every value that stands in for a secret; none of it may reach the output."""

EVERY_TYPE = '''\
# a comment that names an old token, SNTL-comment
top = "SNTL-top"
"dotted.key" = "SNTL-quoted-key"
dotted.path.key = "SNTL-dotted"

[sources.github]
access_token = "<GitHub token>"
quoted = "pa\\"ss SNTL-quoted"
literal = 'SNTL-literal'
multiline = """SNTL-multi
line"""
two_line_placeholder = """<SNTL-two
lines>"""
number = 86753091
decimal = 3.1415
flag = true
day = 2024-01-31
moment = 2024-01-31T12:00:00Z
array = ["SNTL-array", "<in an array>"]
inline = { user = "<user>", password = "SNTL-inline" }
port = 0 # fill this in!

[[sources.github.repos]]
name = "SNTL-aot"
'''
"""A value of every TOML type, a placeholder and a dlt init sample."""

DLT_INIT_SQL_DATABASE = """\
[sources.sql_database.credentials]
drivername = "<configure me>" # fill this in!
database = "<configure me>" # fill this in!
password = "<configure me>" # fill this in!
username = "<configure me>" # fill this in!
host = "<configure me>" # fill this in!
port = 0 # fill this in!
"""
"""The secrets.toml that `dlt init sql_database duckdb` writes in dlt 1.32.0."""

DLT_INIT_FILESYSTEM = """\
[sources.filesystem.credentials]
aws_access_key_id = "<configure me>" # fill this in!
aws_secret_access_key = "<configure me>" # fill this in!

"""
"""The secrets.toml that `dlt init filesystem duckdb` writes in dlt 1.32.0."""

MISPLACED = """\
# Mockshop credentials, from the vendor portal
[sources.mockshop.credentials]
api_token = "SNTL-token"  # rotated 2026-10

[destination.warehouse]
credentials = "SNTL-path"
"""
"""A token under a key dlt does not try, beside a destination."""

DLT_PATHS = """
import json
from pathlib import Path
from dlt.common.runtime import run_context
context = run_context.active()
print(json.dumps([
    str(Path(context.settings_dir, "secrets.toml").absolute()),
    str(Path(context.global_dir, "secrets.toml")),
]))
"""
"""Print the project and global secrets files of dlt's active run context."""


def load_script() -> ModuleType:
    """Import the script as a module, though it sits in no package."""
    spec = importlib.util.spec_from_file_location("dlt_secrets", SCRIPT)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules["dlt_secrets"] = module
    spec.loader.exec_module(module)
    return module


dlt_secrets = load_script()


@pytest.fixture
def home(tmp_path: Path) -> Path:
    """Make a fake home folder, so the real ~/.dlt is never read."""
    path = tmp_path / "home"
    path.mkdir()
    return path


@pytest.fixture(autouse=True)
def project(tmp_path: Path, home: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Run each test in an empty project with no dlt variable set."""
    path = tmp_path / "project"
    path.mkdir()
    monkeypatch.chdir(path)
    monkeypatch.setenv("HOME", str(home))
    for name in list(os.environ):
        if name.startswith(
            ("DLT_", "XDG_DATA_HOME")
        ) or dlt_secrets.DLT_VARIABLE.search(name):
            monkeypatch.delenv(name)
    return path


def write(path: Path, text: str) -> None:
    """Write a file, creating its folder."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def assert_no_secret(text: str) -> None:
    """Fail when any stand-in secret appears in the text."""
    for secret in SECRETS:
        assert secret not in text


def section(out: str, header: str) -> list[str]:
    """Return the lines after a header line, up to the next blank line."""
    lines = out.splitlines()
    start = lines.index(header) + 1
    end = lines.index("", start) if "" in lines[start:] else len(lines)
    return lines[start:end]


def dlt_paths(cwd: Path) -> tuple[Path, Path]:
    """Return the project and global secrets files dlt reads, in a fresh process."""
    env = dict(os.environ, RUNTIME__DLTHUB_TELEMETRY="false")
    result = subprocess.run(
        [sys.executable, "-c", DLT_PATHS],
        cwd=cwd,
        env=env,
        capture_output=True,
        text=True,
        check=True,
    )
    project_file, global_file = json.loads(result.stdout.strip().splitlines()[-1])
    return Path(project_file), Path(global_file)


# show --------------------------------------------------------------------------------


def test_show_prints_only_placeholders_from_both_files(
    project: Path, home: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    write(project / ".dlt" / "secrets.toml", EVERY_TYPE)
    write(home / ".dlt" / "secrets.toml", '[sources.stripe]\napi_key = "SNTL-global"\n')

    assert dlt_secrets.main(["show"]) == 0

    out = capsys.readouterr().out
    assert_no_secret(out)
    assert 'access_token = "<GitHub token>"' in out
    assert 'user = "<user>"' in out
    assert "port = ***  # fill this in!" in out
    assert '"dotted.key" = ***' in out
    for key in ("quoted", "literal", "multiline", "two_line_placeholder", "number"):
        assert f"{key} = ***" in out
    for key in ("decimal", "flag", "day", "moment", "array", "password", "repos"):
        assert f"{key} = ***" in out
    assert f"global file: {home / '.dlt' / 'secrets.toml'}" in out
    assert "api_key = ***" in out


def test_show_reports_missing_files(capsys: pytest.CaptureFixture[str]) -> None:
    assert dlt_secrets.main(["show"]) == 0

    out = capsys.readouterr().out
    assert out.count("(not found)") == 2
    assert "(no keys in the files, and no dlt source or destination variable" in out
    assert out.rstrip().endswith("placeholders left: 0")


def test_show_lists_each_variable_by_state_never_by_value(
    project: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    write(
        project / ".dlt" / "secrets.toml",
        '[sources.github]\naccess_token = "<token>"\n'
        'webhook = "<hook>"\norg = "<org>"\n',
    )
    monkeypatch.setenv("SOURCES__GITHUB__ACCESS_TOKEN", "SNTL-env")
    monkeypatch.setenv("SOURCES__GITHUB__WEBHOOK", "")
    monkeypatch.setenv("GITHUB_PROD__SOURCES__GITHUB__ACCESS_TOKEN", "SNTL-prefixed")
    monkeypatch.setenv("UNRELATED__VARIABLE", "SNTL-unrelated")

    assert dlt_secrets.main(["show"]) == 0

    out = capsys.readouterr().out
    assert_no_secret(out)
    states = {
        line.split()[0]: " ".join(line.split()[1:])
        for line in section(out, "environment variables:")
    }
    assert states == {
        "SOURCES__GITHUB__ACCESS_TOKEN": "set",
        "SOURCES__GITHUB__WEBHOOK": "set (empty)",
        "SOURCES__GITHUB__ORG": "unset",
        "GITHUB_PROD__SOURCES__GITHUB__ACCESS_TOKEN": "set (no key in the files)",
    }


def test_show_counts_the_placeholders_dlt_would_still_read(
    project: Path,
    home: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    write(
        project / ".dlt" / "secrets.toml",
        DLT_INIT_SQL_DATABASE + '[sources.github]\naccess_token = "<token>"\n'
        'webhook = "SNTL-filled"\n[sources.notion]\napi_key = "<notion>"\n',
    )
    write(
        home / ".dlt" / "secrets.toml",
        '[sources.github]\nwebhook = "<shadowed by the project file>"\n'
        '[sources.slack]\ntoken = "<slack>"\n',
    )
    monkeypatch.setenv("SOURCES__NOTION__API_KEY", "SNTL-env")

    assert dlt_secrets.main(["show"]) == 0

    left = section(capsys.readouterr().out, "placeholders left: 8")
    fields = ("drivername", "database", "password", "username", "host")
    assert left == [
        *(f"  sources.sql_database.credentials.{field}" for field in fields),
        "  sources.sql_database.credentials.port (a dlt init sample value)",
        "  sources.github.access_token",
        "  sources.slack.token",
    ]


def test_show_counts_no_placeholder_once_each_is_filled(
    project: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    filled = DLT_INIT_SQL_DATABASE.replace('"<configure me>"', '"SNTL-filled"')
    write(project / ".dlt" / "secrets.toml", filled.replace("port = 0", "port = 5432"))

    assert dlt_secrets.main(["show"]) == 0

    out = capsys.readouterr().out
    assert_no_secret(out)
    assert out.rstrip().endswith("placeholders left: 0")


@pytest.mark.parametrize(
    "sample",
    ["0", "1.0", '"1.0"', '"1768-07-21"', '"1768-07-21T02:56:07.000003Z"', '"key"'],
)
def test_show_counts_a_dlt_init_sample_only_with_its_marker(
    project: Path, capsys: pytest.CaptureFixture[str], sample: str
) -> None:
    path = project / ".dlt" / "secrets.toml"
    write(path, f"[sources.probe]\nkey = {sample} # fill this in!\n")
    assert dlt_secrets.main(["show"]) == 0
    assert "placeholders left: 1\n" in capsys.readouterr().out

    write(path, f"[sources.probe]\nkey = {sample}\n")
    assert dlt_secrets.main(["show"]) == 0
    assert capsys.readouterr().out.rstrip().endswith("placeholders left: 0")


@pytest.mark.parametrize(
    "content",
    [
        b'[sources.github]\naccess_token = "SNTL-unterminated\n',
        b'[sources]\ngithub = "SNTL-value"\n[sources.github]\nkey = 1\n',
        b'[sources]\ngithub.key = "SNTL-dotted"\n[sources.github]\nother = 1\n',
        'token = "SNTL caf\xe9"\n'.encode("latin-1"),
    ],
    ids=[
        "unterminated string",
        "key defined twice",
        "table defined twice",
        "not UTF-8",
    ],
)
def test_show_refuses_an_unreadable_file_without_echoing_it(
    project: Path, capsys: pytest.CaptureFixture[str], content: bytes
) -> None:
    path = project / ".dlt" / "secrets.toml"
    path.parent.mkdir()
    path.write_bytes(content)

    assert dlt_secrets.main(["show"]) == 1

    captured = capsys.readouterr()
    assert captured.out == ""
    assert captured.err.startswith(f"error: {path} is not ")
    assert_no_secret(captured.err)


# add ---------------------------------------------------------------------------------


def test_add_creates_the_file_with_owner_only_permissions(
    project: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    fragment = 'sources.github.access_token = "<GitHub token>"'

    assert dlt_secrets.main(["add", fragment]) == 0

    path = project / ".dlt" / "secrets.toml"
    assert stat.S_IMODE(path.stat().st_mode) == 0o600
    assert tomllib.loads(path.read_text(encoding="utf-8")) == {
        "sources": {"github": {"access_token": "<GitHub token>"}}
    }
    out = capsys.readouterr().out
    assert "added: sources.github.access_token" in out
    assert f"wrote: {path}" in out


def test_add_keeps_every_existing_key_value_comment_and_mode(
    project: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    original = (
        "# project secrets, rotated 2026\n"
        "[sources.github]\n"
        'access_token = "SNTL-token"  # expires 2027\n'
        "\n"
        "[destination.postgres.credentials]\n"
        'password = "SNTL-password"\n'
        "\n"
        "[sources.stripe]\n"
        'api_key = "SNTL-key"'  # no final newline
    )
    path = project / ".dlt" / "secrets.toml"
    write(path, original)
    path.chmod(0o640)
    fragment = (
        '[sources.github]\naccess_token = "<GitHub token>"\n'
        'webhook_secret = "<GitHub webhook secret>"  # repo settings, Webhooks\n'
        '[sources.notion]\napi_key = "<Notion integration secret>"\n'
    )

    assert dlt_secrets.main(["add", fragment]) == 0

    text = path.read_text(encoding="utf-8")
    positions = [
        text.splitlines().index(line) for line in original.splitlines() if line
    ]
    assert positions == sorted(positions)
    assert "# repo settings, Webhooks" in text
    assert stat.S_IMODE(path.stat().st_mode) == 0o640
    assert tomllib.loads(text) == {
        "sources": {
            "github": {
                "access_token": "SNTL-token",
                "webhook_secret": "<GitHub webhook secret>",
            },
            "stripe": {"api_key": "SNTL-key"},
            "notion": {"api_key": "<Notion integration secret>"},
        },
        "destination": {"postgres": {"credentials": {"password": "SNTL-password"}}},
    }
    out = capsys.readouterr().out
    assert_no_secret(out)
    assert "kept: sources.github.access_token (already set)" in out
    assert "added: sources.github.webhook_secret" in out
    assert "added: sources.notion.api_key" in out


@pytest.mark.parametrize(
    "value",
    [
        '"SNTL-string"',
        "86753091",
        "true",
        "2024-01-31",
        '["<a>"]',
        '{ a = "SNTL-inline" }',
        '"""<multi\nline>"""',
        '"<>"',
        '" <padded> "',
    ],
)
def test_add_refuses_a_value_that_is_not_a_placeholder(
    project: Path, capsys: pytest.CaptureFixture[str], value: str
) -> None:
    path = project / ".dlt" / "secrets.toml"
    write(path, '[sources.github]\naccess_token = "<GitHub token>"\n')
    before = path.read_bytes()
    fragment = f'[sources.stripe]\nwebhook = "<ok>"\napi_key = {value}\n'

    assert dlt_secrets.main(["add", fragment]) == 1

    assert path.read_bytes() == before
    captured = capsys.readouterr()
    assert captured.out == ""
    refusal = (
        "refused, nothing written: not a <...> placeholder: sources.stripe.api_key"
    )
    assert refusal in captured.err
    assert "webhook" not in captured.err
    assert_no_secret(captured.err)


@pytest.mark.parametrize(
    ("fragment", "message"),
    [
        ('sources.stripe.api_key = "SNTL-unterminated', "fragment 1 is not valid TOML"),
        ('a = "<a>"\na = "<SNTL-again>"\n', "fragment 1 is not valid TOML"),
        ("# a comment, no key\n", "the fragment holds no key"),
    ],
    ids=["unterminated string", "key defined twice", "no key"],
)
def test_add_refuses_a_bad_fragment_without_echoing_it(
    project: Path, capsys: pytest.CaptureFixture[str], fragment: str, message: str
) -> None:
    assert dlt_secrets.main(["add", fragment]) == 1

    err = capsys.readouterr().err
    assert err.startswith(f"error: {message}")
    assert_no_secret(err)
    assert not (project / ".dlt" / "secrets.toml").exists()


def test_add_never_writes_through_a_value(
    project: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    path = project / ".dlt" / "secrets.toml"
    write(path, '[destination.postgres]\ncredentials = "postgresql://u:SNTL@h/db"\n')
    before = path.read_bytes()
    fragment = 'destination.postgres.credentials.password = "<password>"'

    assert dlt_secrets.main(["add", fragment]) == 0

    assert path.read_bytes() == before
    out = capsys.readouterr().out
    assert_no_secret(out)
    assert "kept: destination.postgres.credentials.password (a parent key holds" in out
    assert f"unchanged: {path}" in out


def test_add_creates_a_table_inside_an_inline_table_as_inline(project: Path) -> None:
    path = project / ".dlt" / "secrets.toml"
    write(path, '[sources]\ngithub = { access_token = "SNTL-inline" }\n')

    assert dlt_secrets.main(["add", 'sources.github.app.key = "<app key>"']) == 0

    assert tomllib.loads(path.read_text(encoding="utf-8")) == {
        "sources": {
            "github": {"access_token": "SNTL-inline", "app": {"key": "<app key>"}}
        }
    }


def test_add_separates_new_tables_and_ends_with_one_newline(project: Path) -> None:
    path = project / ".dlt" / "secrets.toml"
    write(
        path,
        '# secrets\n[sources.github]\naccess_token = "SNTL-token"\n\n'
        '[destination.postgres.credentials]\npassword = "SNTL-password"\n',
    )
    fragment = (
        '[sources.notion]\napi_key = "<notion>"\n'
        '[destination.postgres.credentials]\nhost = "<host>"\n'
        '[destination.bigquery.credentials]\nproject_id = "<project>"\n'
    )

    assert dlt_secrets.main(["add", fragment]) == 0

    text = path.read_text(encoding="utf-8")
    assert '"<notion>"\n\n[destination.postgres.credentials]' in text
    assert 'host = "<host>"\n\n[destination.bigquery.credentials]' in text
    assert text.endswith('project_id = "<project>"\n')


def test_check_round_trip_refuses_what_tomllib_cannot_read() -> None:
    with pytest.raises(
        dlt_secrets.SecretsError, match=r"TOML 1\.0, so nothing was written"
    ):
        dlt_secrets.check_round_trip("", "k = { a = 1,\n b = 2, }\n", ())


def test_add_reads_the_fragment_from_stdin(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    fragment = '[sources.github]\naccess_token = "<token>"\n'
    monkeypatch.setattr(sys, "stdin", io.StringIO(fragment))

    assert dlt_secrets.main(["add"]) == 0

    assert "added: sources.github.access_token" in capsys.readouterr().out


def test_add_without_a_fragment_on_a_terminal_fails(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    class Terminal(io.StringIO):
        def isatty(self) -> bool:
            return True

    monkeypatch.setattr(sys, "stdin", Terminal(""))

    assert dlt_secrets.main(["add"]) == 1

    err = capsys.readouterr().err
    assert "give the fragment as an argument or on standard input" in err


# move --------------------------------------------------------------------------------


def test_move_puts_a_value_under_a_key_dlt_tries(
    project: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    path = project / ".dlt" / "secrets.toml"
    write(path, MISPLACED)
    path.chmod(0o640)
    arguments = ["sources.mockshop.credentials.api_token", "sources.mockshop.api_token"]

    assert dlt_secrets.main(["move", *arguments]) == 0

    assert path.read_text(encoding="utf-8") == (
        "# Mockshop credentials, from the vendor portal\n"
        "[sources.mockshop]\n"
        'api_token = "SNTL-token"  # rotated 2026-10\n'
        "\n"
        "[destination.warehouse]\n"
        'credentials = "SNTL-path"\n'
    )
    assert stat.S_IMODE(path.stat().st_mode) == 0o640
    out = capsys.readouterr().out
    assert_no_secret(out)
    assert out.startswith(f"moved: {arguments[0]} -> {arguments[1]}\nwrote: {path}\n")
    assert "[sources.mockshop]\napi_token = ***\n" in out


@pytest.mark.parametrize(
    "header",
    [
        "[sources.mockshop.credentials] # from the vendor portal\n",
        "[sources.mockshop.credentials]\n# rotated every 90 days\n",
    ],
    ids=["comment on the header", "comment on its own line"],
)
def test_move_keeps_a_table_that_holds_a_comment(project: Path, header: str) -> None:
    path = project / ".dlt" / "secrets.toml"
    write(path, f'{header}api_token = "SNTL-token"\n')
    arguments = ["sources.mockshop.credentials.api_token", "sources.mockshop.api_token"]

    assert dlt_secrets.main(["move", *arguments]) == 0

    assert path.read_text(encoding="utf-8") == (
        f'[sources.mockshop]\napi_token = "SNTL-token"\n\n{header}'
    )


@pytest.mark.parametrize(
    ("original", "source", "target", "expected", "line"),
    [
        (
            '"dotted.key" = "SNTL-q"  # a quoted key\n\n[sources.github]\nx = 1\n',
            '"dotted.key"',
            'sources.github."new.key"',
            {"sources": {"github": {"x": 1, "new.key": "SNTL-q"}}},
            '"new.key" = "SNTL-q"  # a quoted key',
        ),
        (
            '# secrets\n\n[sources]\ngithub = { user = "SNTL-u", token = "SNTL-t" }\n',
            "sources.github.token",
            "token",
            {"token": "SNTL-t", "sources": {"github": {"user": "SNTL-u"}}},
            '# secrets\ntoken = "SNTL-t"\n\n[sources]\n',
        ),
        (
            '[sources]\ngithub = { user = "SNTL-u" }\nplain = "SNTL-p"\n',
            "sources.plain",
            "sources.github.plain",
            {"sources": {"github": {"user": "SNTL-u", "plain": "SNTL-p"}}},
            'plain = "SNTL-p"',
        ),
        (
            "[destination.pg.credentials]\nuse_ssl = true  # the server needs TLS\n",
            "destination.pg.credentials.use_ssl",
            "destination.pg.use_ssl",
            {"destination": {"pg": {"use_ssl": True}}},
            "use_ssl = true  # the server needs TLS",
        ),
        (
            '[sources.github]\ntoken = "SNTL-t"\n[destination.w]\nc = "SNTL-c"\n'
            '[sources.github.app]\nkey = "SNTL-k"  # app key\n',
            "sources.github.app.key",
            "sources.github.app_key",
            {
                "sources": {"github": {"token": "SNTL-t", "app_key": "SNTL-k"}},
                "destination": {"w": {"c": "SNTL-c"}},
            },
            'app_key = "SNTL-k"  # app key',
        ),
        (
            '[sources.shop]\ntoken = "SNTL-t"\n[destination.w]\nc = "SNTL-c"',
            "sources.shop.token",
            "sources.other.deep.token",
            {
                "sources": {"other": {"deep": {"token": "SNTL-t"}}},
                "destination": {"w": {"c": "SNTL-c"}},
            },
            '[sources.other.deep]\ntoken = "SNTL-t"\n\n',
        ),
        (
            '[sources.x]\ntoken = "SNTL-t"  # c\n[destination.w]\nc = "SNTL-c"\n',
            "sources.x.token",
            "token",
            {"token": "SNTL-t", "destination": {"w": {"c": "SNTL-c"}}},
            'token = "SNTL-t"  # c',
        ),
        (
            '[a]\nk = "SNTL-k"\n[b]\nother = "SNTL-o"',
            "b.other",
            "a.other",
            {"a": {"k": "SNTL-k", "other": "SNTL-o"}},
            'k = "SNTL-k"\nother = "SNTL-o"\n',
        ),
    ],
    ids=[
        "quoted keys",
        "out of an inline table",
        "into an inline table",
        "a boolean keeps its comment",
        "a table split across the file",
        "into a new table",
        "to the root",
        "a last line without a newline",
    ],
)
def test_move_reads_back_with_only_that_value_moved(  # noqa: PLR0913
    project: Path,
    capsys: pytest.CaptureFixture[str],
    original: str,
    source: str,
    target: str,
    expected: dict[str, object],
    line: str,
) -> None:
    path = project / ".dlt" / "secrets.toml"
    write(path, original)

    assert dlt_secrets.main(["move", source, target]) == 0

    text = path.read_text(encoding="utf-8")
    assert tomllib.loads(text) == expected
    assert line in text
    assert not text.startswith("\n")
    assert "\n\n\n" not in text
    assert_no_secret(capsys.readouterr().out)


@pytest.mark.parametrize(
    ("source", "target", "message"),
    [
        (
            "sources.github.missing",
            "sources.github.x",
            "refused, nothing written: sources.github.missing is not in ",
        ),
        ("sources.github", "sources.gh", "sources.github is a table, not one value"),
        (
            "sources.github.repos",
            "sources.github.r",
            "sources.github.repos is a table, not one value",
        ),
        (
            "sources.github.access_token",
            "sources.github.plain",
            "sources.github.plain already exists",
        ),
        (
            "sources.github.plain",
            "sources.github.access_token.key",
            "a key above sources.github.access_token.key holds a value",
        ),
        (
            "sources.github.access_token",
            "sources.github.inline.token",
            "an inline table would drop the comment after sources.github.access_token",
        ),
        (
            'sources.github.x = "SNTL-oops"',
            "sources.github.y",
            "the path to move from is not a dotted key path",
        ),
        (
            "sources.github.plain",
            "SNTL value",
            "the path to move to is not a dotted key path",
        ),
    ],
    ids=[
        "missing value",
        "a table",
        "an array of tables",
        "target exists",
        "target under a value",
        "comment into an inline table",
        "a value as the path",
        "not a path",
    ],
)
def test_move_refuses_without_writing_or_echoing(
    project: Path,
    capsys: pytest.CaptureFixture[str],
    source: str,
    target: str,
    message: str,
) -> None:
    path = project / ".dlt" / "secrets.toml"
    write(
        path,
        '[sources.github]\naccess_token = "SNTL-token"  # from GitHub\n'
        'plain = "SNTL-plain"\ninline = { user = "SNTL-user" }\n\n'
        '[[sources.github.repos]]\nname = "SNTL-repo"\n',
    )
    before = path.read_bytes()

    assert dlt_secrets.main(["move", source, target]) == 1

    assert path.read_bytes() == before
    captured = capsys.readouterr()
    assert captured.out == ""
    assert captured.err.startswith("error: ")
    assert message in captured.err
    assert_no_secret(captured.err)


# remove ------------------------------------------------------------------------------


def test_remove_deletes_the_keys_dlt_init_wrote_for_nothing(
    project: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    path = project / ".dlt" / "secrets.toml"
    kept = '# project secrets\n[sources.github]\naccess_token = "SNTL-token"  # 2027\n'
    write(path, f"{kept}\n{DLT_INIT_FILESYSTEM}")
    prefix = "sources.filesystem.credentials"

    assert dlt_secrets.main(["remove", f"{prefix}.aws_access_key_id"]) == 0
    assert '"<configure me>" # fill this in!' in path.read_text(encoding="utf-8")
    assert dlt_secrets.main(["remove", f"{prefix}.aws_secret_access_key"]) == 0

    assert path.read_text(encoding="utf-8") == kept
    out = capsys.readouterr().out
    assert_no_secret(out)
    assert f"removed: {prefix}.aws_secret_access_key\nwrote: {path}\n" in out
    assert dlt_secrets.main(["show"]) == 0
    assert capsys.readouterr().out.rstrip().endswith("placeholders left: 0")


def test_remove_then_add_makes_a_credentials_table_one_key(
    project: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    path = project / ".dlt" / "secrets.toml"
    write(path, DLT_INIT_SQL_DATABASE)
    fragment = 'sources.sql_database.credentials = "<connection string>"'

    assert dlt_secrets.main(["add", fragment]) == 0
    assert "kept: sources.sql_database.credentials (already set)" in (
        capsys.readouterr().out
    )
    assert dlt_secrets.main(["remove", "sources.sql_database.credentials"]) == 0
    assert path.read_text(encoding="utf-8") == ""
    assert dlt_secrets.main(["add", fragment]) == 0

    assert tomllib.loads(path.read_text(encoding="utf-8")) == {
        "sources": {"sql_database": {"credentials": "<connection string>"}}
    }


@pytest.mark.parametrize(
    ("content", "removed", "message"),
    [
        (
            '[sources.github]\naccess_token = "SNTL-token"\n',
            "sources.github.missing",
            "refused, nothing written: sources.github.missing is not in ",
        ),
        (
            '[sources.github]\naccess_token = "SNTL-token"\n',
            "sources.github.access_token.key",
            "sources.github.access_token.key is not in ",
        ),
        (None, "sources.github.access_token", "sources.github.access_token is not in"),
        (
            '[sources.github]\naccess_token = "SNTL-token"\n',
            'sources.github.access_token = "SNTL-oops"',
            "the path to remove is not a dotted key path",
        ),
    ],
    ids=["missing key", "a key under a value", "no file", "a value as the path"],
)
def test_remove_refuses_a_path_that_is_not_there(
    project: Path,
    capsys: pytest.CaptureFixture[str],
    content: str | None,
    removed: str,
    message: str,
) -> None:
    path = project / ".dlt" / "secrets.toml"
    if content is not None:
        write(path, content)

    assert dlt_secrets.main(["remove", removed]) == 1

    if content is None:
        assert not path.exists()
    else:
        assert path.read_text(encoding="utf-8") == content
    captured = capsys.readouterr()
    assert captured.out == ""
    assert message in captured.err
    assert_no_secret(captured.err)


def test_write_change_refuses_what_would_not_read_back(project: Path) -> None:
    path = project / ".dlt" / "secrets.toml"
    document = dlt_secrets.parse_toml('key = "<placeholder>"\n', "fragment 1")

    with pytest.raises(
        dlt_secrets.SecretsError, match="would not read back as intended"
    ):
        dlt_secrets.write_change(path, document, {}, "removed: key")

    assert not path.exists()


# paths and dlt ------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("variables", "home_has_dlt", "project_folder", "global_folder"),
    [
        ({}, False, "project/.dlt", "home/.dlt"),
        ({"DLT_PROJECT_DIR": "elsewhere"}, False, "elsewhere/.dlt", "home/.dlt"),
        ({"DLT_CONFIG_FOLDER": "settings"}, False, "project/settings", "home/settings"),
        ({"XDG_DATA_HOME": "xdg"}, False, "project/.dlt", "xdg/dlt"),
        ({"XDG_DATA_HOME": "xdg"}, True, "project/.dlt", "home/.dlt"),
    ],
    ids=[
        "default",
        "DLT_PROJECT_DIR moves the project file",
        "DLT_CONFIG_FOLDER renames both folders",
        "XDG_DATA_HOME moves the global file",
        "XDG_DATA_HOME yields to an existing ~/.dlt",
    ],
)
def test_paths_agree_with_dlt(  # noqa: PLR0913
    project: Path,
    home: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    variables: dict[str, str],
    home_has_dlt: bool,  # noqa: FBT001
    project_folder: str,
    global_folder: str,
) -> None:
    monkeypatch.setenv("DLT_DATA_DIR", str(tmp_path / "data"))
    for name, folder in variables.items():
        value = folder if name == "DLT_CONFIG_FOLDER" else str(tmp_path / folder)
        monkeypatch.setenv(name, value)
    if home_has_dlt:
        (home / ".dlt").mkdir()

    project_file = dlt_secrets.project_secrets_path(os.environ, Path.cwd())
    global_file = dlt_secrets.global_secrets_path(os.environ)

    assert (project_file, global_file) == dlt_paths(project)
    assert project_file == tmp_path / project_folder / "secrets.toml"
    assert global_file == tmp_path / global_folder / "secrets.toml"


def test_dlt_reads_what_add_writes(project: Path, tmp_path: Path) -> None:
    assert (
        dlt_secrets.main(["add", 'sources.github.access_token = "<GitHub token>"']) == 0
    )
    env = dict(
        os.environ,
        RUNTIME__DLTHUB_TELEMETRY="false",
        DLT_DATA_DIR=str(tmp_path / "data"),
    )
    probe = "import dlt; print(dlt.secrets.get('sources.github.access_token', str))"

    result = subprocess.run(
        [sys.executable, "-c", probe],
        cwd=project,
        env=env,
        capture_output=True,
        text=True,
        check=True,
    )

    assert result.stdout.strip() == "<GitHub token>"


def test_script_runs_from_the_command_line(project: Path) -> None:
    def run(*arguments: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [sys.executable, str(SCRIPT), *arguments],
            cwd=project,
            capture_output=True,
            text=True,
            check=False,
        )

    shown = run("show")
    refused = run("add", 'sources.x.key = "SNTL-plain"')
    added = run("add", 'sources.x.key = "<key>"')
    moved = run("move", "sources.x.key", "sources.y.key")
    removed = run("remove", "sources.y")

    assert shown.returncode == 0
    assert "placeholders left: 0" in shown.stdout
    assert refused.returncode == 1
    assert "not a <...> placeholder: sources.x.key" in refused.stderr
    assert_no_secret(refused.stderr)
    assert [added.returncode, moved.returncode, removed.returncode] == [0, 0, 0]
    assert moved.stdout.startswith("moved: sources.x.key -> sources.y.key\n")
    assert removed.stdout.startswith("removed: sources.y\n")
    assert (project / ".dlt" / "secrets.toml").read_text(encoding="utf-8") == ""
