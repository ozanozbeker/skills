---
description: Python style, from TigerStyle. Safety, then performance, then developer experience, enforced by the repo's tools. Use when writing, reviewing or designing Python code, choosing a dependency, deciding how to check an invariant, or setting up a new repo's tooling.
license: Apache-2.0
name: python-style
---

# Python style

A port of [TigerStyle](https://github.com/tigerbeetle/tigerbeetle/blob/main/docs/TIGER_STYLE.md), TigerBeetle's coding style, Apache-2.0, to Python.
The design goals are the same, in the same order: safety, performance, developer experience.
Two things change.
Python's strength is its ecosystem, so the zero-dependency policy becomes a ladder that climbs to a dependency only when the standard library stops.
And Python strips `assert` under `-O`, so assertion density moves into types, raises at boundaries, and pytest.

Each rule below carries its reason in one sentence.
The long argument and the evidence behind it are in [`sources.md`](sources.md).
Read it when a rule needs defending or when a case is not covered here.

## Steps

1. **Sketch before writing.**
   Name every limit (a loop bound, a batch size, a timeout, a queue depth) and every resource the code touches (network, disk, memory, CPU).
   Name the rung of the dependency ladder each piece sits on.
   Write the sketch down when it is more than a few lines, because the design phase is where a 1000x win is still available and where profiling cannot yet help.
2. **Write the code under the rules below.**
3. **Run the tools, and make them pass.**
   The repo's config is the source of truth: run every hook `prek.toml` lists, then `uv run pytest`.
   Zero warnings, zero ignores added.
   A tool output is a fact, so trust it over your own reading of the code.
   Done means every tool exits 0 and every public function has a test for its positive space and a test for its negative space.

## Safety

### Control flow

- Iterate; never recurse.
  Python has no tail-call elimination, and the default recursion limit is 1000 frames, so recursion over user-sized input raises `RecursionError` in production.
  Use an explicit stack or `collections.deque`.
- Bound every loop.
  Iterate `for` over a finite iterable.
  A `while` carries a counter against a named maximum and raises when it is exceeded.
  An event loop is the exception, and the code says so in a comment.
- Centralize control flow: push `if`s up and `for`s down.
  The parent function holds the branches and the state.
  Helpers compute and return; they take values, not `Optional` values they must check themselves.
  Batch functions are the base case; the scalar call is the special case.
- Split compound conditions into nested `if`/`else`, and give each `if` its `else`, so the reader can verify that the positive and the negative space are both handled.
- State invariants positively.
  Write `if index < count:` with the failure in the `else`, because `if index >= count:` reads against the grain of the loop it guards.
- Keep a function under 70 lines.
  The ruff rules `C901`, `PLR0912` and `PLR0915` bound complexity, branches and statements; keep them on and keep their defaults.
  Good shape is a few parameters, a simple return type, and most of the lines between them.
- Run at your own pace.
  Pull from a queue or a socket in batches on your own schedule rather than doing work inside each callback, so the control flow and the work per second stay under your control.

### Assertions

TigerStyle's rule is two assertions per function, pairs across code paths, and tests that cover the positive and the negative space.
Python has three places for that density, and `assert` in `src/` is none of them: `python -O` strips it, and ruff's `S101` flags it.

- **Types are the compile-time assertions.**
  Annotate every parameter and return.
  The type checker proves the relationship before the code runs, which is what `comptime { assert(...) }` does in Zig.
  Use `Literal` for a set of allowed strings, `Final` for a constant, `typing.assert_never` in the `else` of a `match` so a new variant fails the checker, and `typing.assert_type` in a test when a return type must stay exactly what it is.
- **A `raise` is the runtime assertion in `src/`.**
  Check a precondition at the top of a public function and raise `ValueError` or `TypeError` with the offending value in the message.
  Postconditions and invariants raise too.
  An uncaught exception is the crash TigerStyle asks for: a programmer error must stop the program, not be handled.
  A precondition on a private helper is usually a type instead, because its caller already checked.
- **`assert` lives in tests.** pytest rewrites it to show both sides on failure, and ruff allows it there.
  Write `assert a` then `assert b`, not `assert a and b`, so the failure names the condition.
  Assert an implication as `if a: assert b`.
- **Pair the assertions.**
  The function raises on a bad input; the test asserts that it raises, with `pytest.raises(ValueError, match=...)`.
  Validate data before it is written and again after it is read.
  Where a producer and a consumer meet, test both sides of the contract against the same example.
- **Assert the positive space and the negative space.**
  Every public function gets a test with valid input and a test with invalid input, and a parametrized case that walks across the boundary (empty, one, the maximum, the maximum plus one).
  Bugs live where valid becomes invalid.
- A property test with hypothesis is the fuzzer.
  It proves the presence of bugs, never their absence, so build the mental model first, encode it as types and raises, then let the fuzzer check the model.
- A blatantly true check is stronger documentation than a comment when the condition is critical and surprising.
  Write it as a test.
- Pair the types too, with a typing test.
  A public type is API, so `tests/typing/` holds code a caller would write: `assert_type` on each public attribute and return for the positive space, and a call that must fail for the negative space, marked `# ty: ignore[<rule>]`.
  ty's `unused-ignore-comment` fails the check when the error behind that mark stops firing, so a widened `Literal`, an unfrozen field, or a keyword that leaks between models breaks the hook before a release.
  pytest cannot see any of these, because the runtime accepts the bad value or raises a different error.

### Scope and state

- Build resources at startup, then pass them in.
  Open the connection, compile the regex, load and validate the config, and create the client once in `main` or the app factory.
  A bad environment then fails before any work starts, and every function receives what it needs as a parameter.
  Module-level mutable state is the Python equivalent of allocation after init.
- Declare a variable at the smallest scope, as close to its use as possible, and let it go out of scope when its use ends.
  The gap between the place of check and the place of use is where a stale value gets used.
- Hold one reference to mutable state.
  A second name for the same list or dict is an alias that goes stale.
  Freeze what can be frozen: `@dataclass(frozen=True)`, tuples, `frozenset`.
- Keep a check and its use on the same side of an `await`.
  A precondition verified before a suspension point may be false after it.
- Prefer the simpler return type.
  `None` beats `bool`, `bool` beats `int`, `int` beats `int | None`, and `int | None` beats raising, because every extra case propagates to every caller.

### Errors

Almost all catastrophic failures in the OSDI 2014 study of distributed systems came from mishandled non-fatal errors, and a third of those were three trivial patterns: an empty or log-only handler, an abort on an over-broad catch, and a `TODO` in the handler.

- Catch the narrowest exception you can name and either handle it or re-raise it. ruff's `BLE001`, `E722`, `S110` and `TRY` rules enforce this; keep them on.
- A handler that only logs has swallowed the error.
  Log and re-raise, or handle and return a value the caller checks.
- `contextlib.suppress` is a handler too.
  It needs the narrowest exception and a comment saying why ignoring it is correct.
- Check every return value that can signal failure, and pass `check=True` to `subprocess.run`.

### Explicit options

Pass the option that changes semantics at the call site, even when the default is what you want today, because a library can change its default and the call site then fails silently. ruff enforces the common cases: `encoding=` for `open` (`PLW1514`), `strict=` for `zip` (`B905`), `check=` for `subprocess.run` (`PLW1510`), `timeout=` for HTTP calls (`S113`).
Apply the same rule to `separator=`, `schema=`, `newline=`, `exist_ok=` and any option whose default you would have to look up.

## Performance

- Sketch first.
  Estimate the four resources (network, disk, memory, CPU) on bandwidth and latency before writing, and land within 90% of the optimum by design rather than by profiling afterwards.
- Optimize the slowest resource first, weighted by how often it is used: network, then disk, then memory, then CPU.
- Batch.
  Amortize a network round trip, a disk write, a DataFrame operation over many items.
  In Python this also means staying inside the vectorized library: one polars expression over a column, never a Python loop over rows.
- Separate the control plane from the data plane.
  Decide once per batch, then run a straight-line loop over the batch.
  This is where the `if`-outside, `for`-inside shape pays off.
- Extract a hot loop into a standalone function with primitive arguments and no `self`, so a reader can see every computation and the interpreter does no attribute lookups inside it.

## Developer experience

### Dependencies

The ladder.
Stop at the first rung that holds, and look before writing, because reimplementing what a module a few files away already does is the most common form of waste.

1. Does it need to exist at all?
   Speculative need: say so in one line and skip it.
2. Already in this codebase?
   Reuse it.
3. In the standard library?
   Use it.
   `pathlib`, `dataclasses`, `enum`, `itertools`, `functools`, `collections`, `json`, `tomllib`, `datetime`, `logging`, `argparse`, `subprocess`, `contextlib`, `typing`, `statistics`, `sqlite3`, `csv`, `re`, `hashlib`, `secrets`, `uuid`, `textwrap`, `shutil` and `tempfile` cover most of what a hand-rolled helper does.
4. Already installed in this project?
   Use it, and prefer the typed library over the untyped one.
5. A new dependency, when the library is the right tool and the code would otherwise reimplement it: fastapi, polars, pydantic, httpx, dataframely.
   Weigh annotation-driven typing above install size, and put a heavy library behind an extra.
6. Only then, the minimum code that works.

Every abstraction has a cost, and the cost is never zero: install size, import time, lock churn, and code you have not read.
A dependency is also a trust decision.
Keep abstractions to the minimum that makes the best sense of the domain: an interface with one implementation, a factory with one product, a config for a value that never changes, and a wrapper that only delegates each add a layer the reader has to see through.

Confine a dependency that the codebase wraps to the one module that wraps it, and make the confinement mechanical.
ruff's `banned-api` fails any other import with a message that names the ADR, the module's docstring states that it is the only importer, and `per-file-ignores` lists the allowed files, so the seam is reviewable in config.
A parser, an HTTP client, a CLI framework and a database driver each earn this: an upstream change then touches one file, and a pre-pass that works around an upstream bug has one home.

### Tooling

A small standardized toolbox.
Each tool gives a deterministic answer, so run the tool instead of reading the code for the same answer, and treat its output as a fact.

| Job | Tool |
| --- | --- |
| Project, environment, lock, run | `uv`: every project starts from `uv init --lib` or `uv init --app`, so it has the `src/` layout and a build backend |
| Lint and format Python | `ruff` with `select = ["ALL"]` |
| Type check | `ty`, with `error-on-warning` and its stricter rule set |
| Test | `pytest`, with `filterwarnings = ["error"]` |
| Markdown | `rumdl` |
| TOML | `tombi` |
| Hooks | `prek`, with every `rev` a frozen SHA |

[`setup.md`](setup.md) maps the config files a new repo starts from, by kind of repo, to the Copier answers in the `templates` repo that holds them with the reason for each setting.
Read it when setting up a repo or when a repo's config departs from the table above.
What happens after `git push` (the pull request, CI, the release) is the `github-style` skill's.

Zero warnings from day one, at the strictest setting.
When a tool complains and you believe it is wrong, rewrite the code so the tool agrees, because a warning assumed invalid is usually valid for a reason not yet seen.
An ignore comment carries the reason beside it and is the exception, never the fix.

Write `scripts/*.py`, not `scripts/*.sh`.
A Python script with PEP 723 inline metadata runs under `uv run` on every platform, is typed and linted, and fails the same way for everyone on the team.

### Naming

- Get the nouns and verbs right.
  A name captures what the thing is or does and shows that the author understands the domain.
  Take the time.
- `snake_case` for functions, variables, modules and files; `PascalCase` for classes; acronyms keep their capitals (`HTTPClient`, `VSRState`). ruff's `N` rules hold this.
- Write the whole word.
  Abbreviate only a loop index or a matrix dimension.
  Scripts take long flags: `--force`, not `-f`.
- Units and qualifiers go last, in descending significance: `latency_ms_max`, so `latency_ms_min` lines up beside it and both sort together.
- Related names get the same length where you can: `source` and `target`, so `source_offset` and `target_offset` line up.
- Prefer a noun to a participle, because a noun composes: `replica.pipeline`, then `config.pipeline_max`.
- Give one meaning per name.
  A term the domain already uses keeps that meaning.
- Name a helper after its caller to show the call history: `read_sector` and `read_sector_callback`.
  A callback is the last parameter, because it runs last.
- Keyword-only arguments after `*` for any two parameters of the same type, and for every boolean (ruff `FBT`).
  Name a parameter that accepts `None` so the meaning of `None` at the call site is plain.
- Order a file top-down by importance: `main` or the public entry point first.
  In a class, fields, then nested types, then methods.
  When no order is better than another, sort alphabetically.

### Comments and commits

- Say why.
  Code is not documentation of its own rationale.
  A comment is one line, records a reason the code does not show, and is a sentence with a capital and a full stop.
- Say how, at the top of a test: the goal and the method, so a reader can skip the body.
- A commit message is read, and `git blame` shows it where a pull request description never appears.
  Write the message for that reader.

### Off-by-one

- An `index`, a `count` and a `size` are three types that happen to share `int`.
  Index to count adds one.
  Count to size multiplies by the unit.
  Put the word in the name.
- Show intent in division: `//`, `divmod`, `math.ceil`, or a check that the division is exact.

### Formatting

`ruff format` decides.
Four spaces, trailing commas to wrap, and the line length the repo's ruff config sets.
Nothing hides behind a horizontal scrollbar.
