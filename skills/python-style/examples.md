# Examples

Two rules in [`SKILL.md`](SKILL.md) are easier to follow from code than from prose.

## Typing tests

`tests/typing/` holds one file per public surface, as code a caller would write.
The positive space is `assert_type` on each public attribute and return.
The negative space is a call that must fail, marked with the rule that fails it:

```python
"""Code a caller writes against the payloads, which `ty check` checks."""

from typing import Literal, assert_type

import <package> as pkg

payload = pkg.Payload(source="universal", url="https://example.com")
assert_type(payload.render, Literal["html", "png", ""] | None)

pkg.Payload(source="universal", url="https://example.com", render="htm")  # ty: ignore[invalid-argument-type]
pkg.Payload(url="https://example.com")  # ty: ignore[missing-argument]
payload.url = "https://example.org"  # ty: ignore[invalid-assignment]
```

`unused-ignore-comment` at `error` makes each marked line fail the hook when its error stops firing, so the file asserts both spaces with the main `ty check` and needs no second hook.
A widened `Literal`, an unfrozen field, or a keyword that leaks between models then breaks the hook before a release.

## Confining a dependency

A dependency the package wraps is confined to its wrapper module:

```toml
[lint.flake8-tidy-imports.banned-api]
"sqlglot".msg = "Only `<package>._read` imports sqlglot (ADR 0004)."

[lint.per-file-ignores]
# Each module that may import a banned library, with the ADR that allows it.
"src/<package>/_read.py" = ["TID251"]
```

The wrapper's module docstring states that it is the only importer, so the config and the code assert the same seam.
