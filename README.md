# jointhestudentlife

Official Python SDK for [The Student Life](https://jointhestudentlife.com): student events, ticket prices, city guides and student deals in 85+ cities, for international and exchange students.

The API is open. No key, no signup, no payment. Standard library only, Python 3.9+.

```sh
pip install jointhestudentlife
```

```python
from jointhestudentlife import TheStudentLife

tsl = TheStudentLife()
events = tsl.events(city="paris", type="halloween")["events"]
print(events[0]["tickets"]["options"])  # [{'name': 'Round 1', 'price': 9.5, 'currency': 'EUR'}, ...]

guide = tsl.city("lisbon")
for city in tsl.each_city():
    print(city["name"])

# async report job: 202 Accepted, then poll until it succeeds
job = tsl.run_report("city_comparison", cities=["berlin", "lisbon"])
print(job["result"]["cities"][0]["monthly_costs"])
```

Methods: `info`, `cities`, `city`, `events`, `event`, `partners`, `pricing`, `each_city`, `each_event`, `create_report`, `get_report`, `run_report`, `send_message`. Lists are cursor paginated (`next_cursor`). Errors raise `TheStudentLifeError` with `status` and `code` (including `timeout` and `network_error`). Requests retry on 429 (honouring `Retry-After`); reads also retry on 5xx, while a message is only retried when it carries an idempotency key, so it is never sent twice by the SDK. Requests time out after 30 seconds (`timeout`).

`send_message` emails our team on someone's behalf. Only use it with that person's consent and their own name and email. Pass `dry_run=True` to validate without sending, and a fresh `idempotency_key` per message so a retry is recognised (best effort, see the developer docs). Messages are limited to a few per minute.

There is also an MCP server at `https://jointhestudentlife.com/mcp`, a JavaScript SDK and CLI on npm (`jointhestudentlife`), and the OpenAPI spec at `https://jointhestudentlife.com/openapi.json`. Full docs: https://jointhestudentlife.com/developers

## Licence

The MIT licence covers the code of this package only. The data the API returns, the website content and The Student Life name and logo stay with Socials BV.
