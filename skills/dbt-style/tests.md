# Custom generic tests

Source: [writing custom generic data tests](https://docs.getdbt.com/best-practices/writing-custom-generic-tests).
When the [dbt-labs/dbt-agent-skills](https://github.com/dbt-labs/dbt-agent-skills) skills are installed, `using-dbt-for-analytics-engineering` decides which tests a model gets, and `adding-dbt-unit-test` owns unit tests.
This file is the mechanics of a generic test.

- Check `dbt_utils` and `dbt_expectations` first, because the test usually exists.
- A singular test in `tests/` is a draft: once its logic settles, turn it into a generic test or find one in a package.
- A generic test lives in `tests/generic/` (the `generic` subfolder of `test-paths`), or in `macros/` when it depends on macro logic defined in the same file.
- Define it as a test block; a returned row is a failure, zero rows pass:

  ```sql
  {% test <name>(model, column_name) %}

      select *
      from {{ model }}
      where {{ column_name }} ...

  {% endtest %}
  ```

- The first argument is always `model`, even when the resource is a source, seed or snapshot.
  Include `column_name` only for a column-level test.
- Extra arguments go in the signature, `{% test relationships(model, column_name, field, to) %}`, and in YAML under `arguments:`.
  `model` and `column_name` come from context and never appear in YAML.
- A `{{ config(severity = 'warn') }}` inside the test block sets a default for every instance; an instance overrides it in its own config.
- A test block named after a built-in, `{% test unique(model, column_name) %}`, overrides dbt's implementation.
- Document it under `macros:` in `tests/generic/schema.yml` as `test_<name>`, with an `arguments:` list giving `name`, `type` and `description` per argument.
- Call it under `data_tests:` on a model, source, snapshot or seed; an instance may carry its own `description:`.
