# REST API pipelines

How to build a pipeline on the `rest_api` core source or over `RESTClient`, one endpoint at a time, and how to read its failures.
Source: the [REST API source](https://dlthub.com/docs/dlt-ecosystem/verified-sources/rest_api/basic), [REST API helpers](https://dlthub.com/docs/dlt-ecosystem/verified-sources/rest_api/advanced), the [REST API tutorial](https://dlthub.com/docs/tutorial/rest-api) and the [CLI reference](https://dlthub.com/docs/reference/command-line-interface).

## Choosing the source

- Use `rest_api` when no verified source covers the API, because one typed dict states each endpoint's pagination, cursor and key where a reviewer can read them, and a paginator the built-ins lack plugs in as a `BasePaginator` subclass instance.
- Write a `@dlt.resource` over `RESTClient` only for a request flow the config cannot state, such as an export job you start, poll and download; `RESTClient.paginate()` keeps dlt's paginators and retries.

## Steps

These steps refine step 4 of [`SKILL.md`](SKILL.md) for each endpoint, and its steps 5 and 6 follow them.

1. **Run one endpoint for one page as a throwaway run.**
   Fetch one response yourself with `curl`, and write the endpoint's `data_selector` and `paginator` from it, because a wrong selector loads nothing and raises nothing.
   Pass the token from `.dlt/secrets.toml` through a process substitution, so neither the command line nor the output holds it, and leave out `-v`, which prints the header:

   ```bash
   curl -s -H @<(uv run python -c 'import dlt; print("Authorization: Bearer " + dlt.secrets.get("sources.shop.token", str))') "<base_url>/orders?limit=1"
   ```

   In the example's `__main__` below, set `dev_mode=True`, run `shop().with_resources("orders").add_limit(1)`, and start the script with `RUNTIME__LOG_LEVEL=INFO uv run python <script>.py`, which overrides the `WARNING` level `uv run dlt init` writes.
   Done means the log shows one `Making GET request to` line with the query string you expect, no paginator WARNING, and rows in the table.
2. **Read the endpoint in full: drop `add_limit`, keep `dev_mode`, and run again.**
   Done means `count(distinct id)` equals `count(*)`, the count matches the API's own total when it reports one, and the endpoint's last log line ends `does not have more pages`.
3. **Add the next endpoint the same way, one at a time.**
   Run steps 1 and 2 for it, under [Child endpoints](#child-endpoints) when it is a child.
   A child's step 1 runs `shop().with_resources("orders", "order_items").add_limit(1)`, and `add_limit` sets its limit on the parent, so the run reads one page of orders and requests the items of every order on it.
   Done means every endpoint passed step 2, a child's step 1 logged one parent request followed by the child's requests for each row on that page, and a full run of the source logs no paginator WARNING.

## Example

```python
from collections.abc import Iterator

import dlt
import polars as pl
from dlt.sources import DltResource
from dlt.sources.rest_api import RESTAPIConfig, rest_api_resources


@dlt.source(name="shop", section="shop")
def shop(base_url: str = dlt.config.value, token: str = dlt.secrets.value) -> Iterator[DltResource]:
    config: RESTAPIConfig = {
        "client": {"base_url": base_url, "auth": {"type": "bearer", "token": token}},
        "resource_defaults": {"primary_key": "id", "write_disposition": "merge"},
        "resources": [
            {
                "name": "orders",
                "endpoint": {
                    "path": "orders",
                    "data_selector": "orders",  # the key that holds the list in this API's responses
                    "params": {"limit": 100, "updated_since": "{incremental.start_value}"},
                    "paginator": {"type": "cursor", "cursor_path": "next_cursor", "cursor_param": "cursor"},
                    "incremental": {"cursor_path": "updated_at", "initial_value": "2026-01-01T00:00:00Z"},
                },
            },
            {
                "name": "order_items",
                "primary_key": ["_orders_id", "line_no"],
                "merge_key": "_orders_id",
                "include_from_parent": ["id"],
                "endpoint": {"path": "orders/{resources.orders.id}/items", "data_selector": "items", "paginator": "single_page"},
            },
        ],
    }
    yield from rest_api_resources(config)


if __name__ == "__main__":
    pipeline = dlt.pipeline(pipeline_name="shop", destination="duckdb", dataset_name="shop_raw", dev_mode=False)
    print(pipeline.run(shop()))
    keys = pipeline.dataset()("select count(*) as row_count, count(distinct id) as id_count from orders")
    print(pl.DataFrame(keys.arrow()))
```

This ran as written against a mock API, and it is the shape of a production source: copy the structure, and take every path, selector and cursor from your API's own responses.
[`production.md`](production.md) adds the named destination, retries and monitoring around it.
With `section="shop"`, both arguments resolve from `[sources.shop]`: `base_url` in `.dlt/config.toml` and `token` in `.dlt/secrets.toml`, which [`secrets.md`](secrets.md) writes without showing the token.

## The config

- Build the config inside a `@dlt.source` function and type it `RESTAPIConfig`, so credentials arrive as injected arguments and the editor checks the shape.
  dlt validates the dict when the source is built and names the bad path, such as `received unexpected fields` with `{'params'}` for `params` set beside `endpoint`.
- Put query params every endpoint shares in `resource_defaults.endpoint.params`, because `params` and `json` merge into each endpoint's own, while every other key there, `paginator` included, is replaced whole by an endpoint that sets it.
- Pass credentials only through `auth`, because at `log_level = "DEBUG"` dlt prints each request's `headers` and `params` as written, a token in `headers` included, and leaves `auth` out.
  `auth` takes `bearer`, `api_key`, `http_basic` or `oauth2_client_credentials`; `api_key` goes in the `Authorization` header unless you set its `name` and `location` (`header` or `query`).
- Send a key in a header whenever the API accepts one, because every INFO `Making GET request to` line prints the URL, and dlt masks only the query params named `api_key`, `token`, `key`, `apikey` and `access_token`.
  A key that must go in the query string goes under `auth` with `location: query`; then treat the INFO logs, and the errors of any endpoint with `response_actions`, as holding the secret, because those errors skip dlt's masking and reach the trace and `pipeline.last_trace`.
- `processing_steps` (`filter`, `map`, `yield_map`) run in order before the incremental, so a `filter` holds the cursor at the last kept row, and a `map` of the cursor sets the type `initial_value` must have, under [Incremental](#incremental).

## Paginators

Set `paginator` on every endpoint, because auto-detection guesses from the first response and logs only a WARNING when it guesses.
It read a 1-based page API as 0-based, loading page 1 twice and never the last page, and an offset API with only a `total` count as one page, and both runs reported success.
A `paginator` or `data_selector` set once in `resource_defaults.endpoint` counts as set on every endpoint that does not set its own, children included.

| `type` | Stops when | Trap |
| --- | --- | --- |
| `page_number` | the next page passes the count at `total_path`, reaches `maximum_page`, `has_more_path` is false, or a page comes back empty | `base_page` defaults to `0`; `total_path` defaults to `"total"`, and a response without that key fails with `not found in the response in`, so set `"total_path": None` |
| `offset` | the next offset passes the count at `total_path`, reaches `maximum_offset`, `has_more_path` is false, or a page comes back empty | `limit` is required; `total_path` defaults to `"total"` here too |
| `cursor` | the value at `cursor_path` is null or empty, or `has_more_path` is false | `stop_after_empty_page` defaults to `False`, so an API that repeats its last page cursor loops |
| `json_link`, `header_link` | the next link is absent | the next URL replaces the query string, so a param you added survives only if the API echoes it |
| `single_page` | after one request | none; it is the right choice for a one-page child |

- Set `maximum_page` or `maximum_offset` one past the last page or offset you want, because both are exclusive: `maximum_page: 3` with `base_page: 1` read pages 1 and 2.
- When the API's next link drops your params, subclass `JSONLinkPaginator`, re-set `request.params` in `update_request`, and pass the instance as `paginator`; it kept `per_page` and `updated_since` on every page.

## Child endpoints

- A `{resources.<parent>.<field>}` placeholder in `path`, `params`, `json` or `headers` makes the endpoint a child, with one request per parent row; a field the parent lacks fails the extract with `Available parent fields are` and the list.
- `include_from_parent: ["id"]` adds the parent's field as `_<parent>_<field>`, here `_orders_id`; key the child on it with its own `primary_key`, because `resource_defaults` reaches children too, and a child without the default `id` failed normalize with `did not receive any data during this load`.
- Give a child whose rows can vanish at the source, such as an order's lines, `"merge_key": "_orders_id"` beside its `primary_key`, because `delete-insert` then deletes the stored rows of each parent the load has rows for before it inserts, so a removed line disappears, while under `primary_key` alone it stayed.
  A parent whose list comes back empty loads no row, so its old rows stay.
- Set `"paginator": "single_page"` on a one-page child, because without it every parent row logs the fallback-paginator WARNING.
- A path that ends in a placeholder, such as `pokemon/{resources.pokemon.name}`, is read as one entity, with `single_page` and the `$` selector chosen for you.
- A 404 for one parent fails the run; add `"response_actions": [{"status_code": 404, "action": "ignore"}]` to a child whose parents can vanish.
- With an incremental parent, the child requests only the new and changed parents, so fetch a child this way only when its rows change together with the parent's cursor.

## Incremental

- Write the cursor as `{incremental.start_value}` plus an `incremental` block with `cursor_path` and `initial_value`, as the example does; the placeholder works in `path`, `params`, `json` and `headers`, and `{incremental.end_value}` with an `end_value` bounds a backfill, under the cursor rules in [`incremental.md`](incremental.md).
- An `incremental` block without the `{incremental.start_value}` placeholder filters rows only after reading them, so an endpoint the API cannot filter reads every page on every run; give it `merge` with that client-side cursor to load only the changed rows, or `replace` with no `incremental` block for a small table.
- The docs deprecate `{"type": "incremental"}` inside `params` and `start_param` or `end_param` in the block; both still run without a warning in 1.32.0, so rewrite them to the placeholder when you touch the endpoint.
- Keep the cursor as the API's string when every value has one ISO 8601 shape, under the string-cursor rule in [`incremental.md`](incremental.md#the-cursor), and write `initial_value` in that shape, because dlt compares raw response values: a `datetime` `initial_value` against string values failed with `IncrementalCursorInvalidCoercion` and went out as `2026-10-03 00:00:00+00:00`.
- When the shape varies, with fractional seconds on some values or no zone, map the cursor to `datetime` in `processing_steps`, give `initial_value` as a `datetime`, and format the placeholder with `convert`, because strings compare character by character.
  That map with a string `initial_value` fails with `IncrementalCursorInvalidCoercion` (`Could not coerce`), while a `datetime` one plus `convert` loaded every row, one ending `.500Z` included.
- `convert` in the block changes what the placeholder sends (`lambda value: value[:10]` sent `2026-10-03`), while dlt still filters rows on the full value; the older key `transform` fails validation.
- Pair the cursor with `merge` on the primary key, because a changed row comes back under its old key and `merge` replaces the old version; the boundary row an inclusive `since` filter re-sends is dropped by the hash dlt stored.

## Rate limits and retries

dlt's HTTP client retries 429, every 5xx, connection errors and timeouts, and fails at once on any other 4xx: one request each for a 401, a 403 and a 404.
It waits the `Retry-After` seconds when the response sends them, and otherwise 1, 2, 4 and 8 seconds.

| `[runtime]` key | Default | Meaning |
| --- | --- | --- |
| `request_timeout` | `60` | Seconds per attempt; a timeout is retried |
| `request_max_attempts` | `5` | Attempts in total, the first included |
| `request_backoff_factor` | `1` | Multiplier on the 1, 2, 4, 8 second waits |
| `request_max_retry_delay` | `300` | Cap on every wait, `Retry-After` included |

- Raise `request_max_attempts` for an API that sends no `Retry-After` and whose rate window outlasts the 15 seconds the default waits add up to, because the last 429 fails the run.
- To stay under a documented rate, put a callable that sleeps and returns the response into the endpoint's `response_actions`: it runs on every response, and a 0.25 second sleep spaced requests 0.26 seconds apart, at the cost of that endpoint's error text, which then shows no response body and an unmasked URL; parallel child requests and the other speed levers are in [`performance.md`](performance.md).

## Testing

- Mock HTTP at the `requests` level with the `requests_mock` fixture of `requests-mock` (`uv add --dev requests-mock`), so the test runs dlt's paginator and incremental code: a mocked `page_number` endpoint was called once per page, the empty last page included.
- Give the fixture a list of responses for one URL to test retries and `Retry-After`: a 429 with `Retry-After: 3`, then a 200, made two calls 3.0 s apart.
- Make the mock case-sensitive, because by default requests-mock lowercases the path and the query it hands a callback, so a stored cursor reads `2026-10-01t00:00:04z` in `request.qs`.
  For the `requests_mock` fixture set `requests_mock_case_sensitive = true` in `pytest.ini`, and build a mocker of your own as `requests_mock.Mocker(case_sensitive=True)`, because the ini key does not reach it.

## Failure signatures

Run with `RUNTIME__LOG_LEVEL=INFO` to see every request but not its retries; the generic debugging loop is in [`debugging.md`](debugging.md).

| Signature | Cause | Fix |
| --- | --- | --- |
| The same `cursor=` value repeats in `Making GET request to` lines and the run never ends | The API returns its last page cursor again with an empty page | `"stop_after_empty_page": True` on the `cursor` paginator |
| The page number climbs, the same rows come back, the run never ends | The API ignores the `page_param` you set | Set `page_param` to the API's own name |
| No error, the table is missing from `row_counts`, INFO shows `with length 0` | A wrong `data_selector` | Point it at the list in a real response |
| `401 Client Error: Unauthorized for url` or `403 Client Error: Forbidden for url` at `step=extract` | A missing or wrong credential, the wrong `auth` type, or a missing scope | On an endpoint without `response_actions`, set `RUNTIME__HTTP_SHOW_ERROR_BODY=true` to read the API's reason; then fix the secret or the scope |
| WARNING `Please provide paginator manually` or `Please verify the` paginator settings | Detection fell back to one page, or guessed `page_number` or `cursor` | Set the paginator |
