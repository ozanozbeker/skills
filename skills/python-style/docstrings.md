# Docstrings

A docstring follows [numpydoc](https://numpydoc.readthedocs.io/en/latest/format.html).
ruff's `D` rules hold the layout, and numpydoc's validation holds that every public object documents every parameter, its return value and one example.
This page holds what neither tool checks.
A function docstring that passes both and follows this page:

```python
def read_config(path: Path, *, strict: bool = True) -> Config:
    """Read a TOML file and apply every default.

    Parameters
    ----------
    path
        The file to read. A relative path resolves against the working directory.
    strict
        Raise on a key the schema does not name instead of dropping it. Defaults to True.

    Returns
    -------
    :
        The config with every default applied.

    Raises
    ------
    FileNotFoundError
        When `path` does not exist.
    ValueError
        When `strict` is True and the file holds a key the schema does not name.

    Examples
    --------
    ```python
    from mypkg import read_config
    from mypkg.data import example_config

    read_config(example_config)
    ```
    """
```

## What the tools cannot see

- The annotation carries the type, so the docstring omits it, because a type in the docstring overwrites the annotation on the rendered page.
  Write the parameter name alone, then an indented description.
- A `Returns` entry has no name and, under the rule above, no type, so its first line is a bare `:` and the description sits indented under it:

  ```text
  Returns
  -------
  :
      The parsed config, with every default applied.
  ```

  A description written on the first line instead passes numpydoc, and griffe and Sphinx's napoleon render it as the return type with no description.
- A summary line is imperative: `Wrap`, not `Wraps`.
  D401 and SS05 read the first word only.
  A class docstring describes what the instance represents and is exempt.
- A `Parameters` entry says what the name and the annotation cannot, and names the default.
- Every exception the function raises has a `Raises` entry.
  No check counts them.
- A parameter forwarded unchanged to another library is covered by one sentence in the extended summary, and the `def` line takes `# numpydoc ignore=PR01` with the reason on the line above:

  ```python
  # PR01: the keyword parameters are `@dg.asset`'s, documented there.
  def asset(name: str, **kwargs: Unpack[AssetKwargs]) -> Asset:  # numpydoc ignore=PR01
      """Define an asset.

      Every keyword parameter but `name` is `@dg.asset`'s, passed to it unchanged.

      Parameters
      ----------
      name
          The asset key.
      """
  ```

  The ignore comment ends after the codes: `# numpydoc ignore=PR01 - reason` reads as the code `PR01 - reason` and ignores nothing (measured with numpydoc 1.11.0, 2026-10-20).
- Constructor parameters go on the class docstring, which numpydoc checks against `__init__`'s signature, and `__init__` takes none.
  An attribute takes its own docstring, below, and the class docstring has no `Attributes` section: griffe renders the attribute docstrings as that table, so the section would say each sentence twice.

  ```python
  class Client:
      """A connection to one server.

      Parameters
      ----------
      url
          The server's base URL, scheme included.
      timeout_s
          Seconds to wait for each reply. Defaults to 30.
      """

      def __init__(self, url: str, *, timeout_s: float = 30) -> None:
          self.url = url
          """The base URL, as given."""
          self._timeout_s = timeout_s
  ```

  A dataclass or pydantic field is the same: the field's docstring, not an `Attributes` entry and not only a `Field(description=...)`.
- A method decorated with `@override` takes a docstring only when its behaviour differs from the base, and then only the difference.
- An attribute takes a docstring, not a comment, on the line after its assignment: a module constant, a class attribute, a dataclass field, a `self` attribute set in `__init__`, or anything else a name is bound to.
  The language servers show that string on hover and the docs tools render it, where a comment reaches neither, and a comment between two assignments reads as belonging to either:

  ```python
  _CLOSING = 421
  """RFC 5321: the server closes its socket after this reply."""
  ```

## Examples

One call that shows the return value is enough.
The code goes in a plain fenced block tagged `python`, which ruff's `docstring-code-format` formats, with no output comment: a written output goes stale, and a docs build that runs the block prints the real value.

Keep the example runnable for any user who has the package installed.
Import example data the package ships, as dplyr's examples use `starwars`, or define what the snippet references.
A demo or test module is not importable from an example.
