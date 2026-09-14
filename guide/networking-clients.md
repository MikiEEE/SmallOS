# Networking Clients

[Previous: Execution adapters](execution-adapters.md) · [Guide home](README.md) ·
[Next: Shell and TCP servers](shell-and-server.md)

smallOS includes cooperative, dependency-free helpers for common protocols:

- `SmallStream` for raw TCP/TLS byte streams
- `SmallHTTPClient` and `SmallSSEClient`
- `SmallRedisClient`
- `SmallMQTTClient`
- `SmallWebSocketClient`

They suspend on smallOS kernel readiness instead of owning an asyncio loop or
starting background threads.

## HTTP example

```python
from SmallPackage import SmallHTTPClient, SmallOS, SmallTask, Unix


async def fetch_status(task):
    client = SmallHTTPClient(task, base_url="https://example.com")
    response = await client.get("/", params={"demo": True})
    task.OS.print("{} {}\n".format(response.status_code, response.reason))
    return response.ok


runtime = SmallOS().setKernel(Unix())
runtime.fork([SmallTask(2, fetch_status, name="fetch_status")])
runtime.startOS()
```

HTTP currently supports common request methods, query parameters, form and
JSON bodies, TLS, and content-length, chunked, or connection-close responses.

Redis supports RESP commands plus helpers such as `ping`, `get`, `set`,
`delete`, `publish`, and `subscribe`. MQTT 3.1.1 supports connect, disconnect,
publish, subscribe, and inbound-message acknowledgement flows at QoS 0, 1,
and 2.

Clients accept explicit limits and transport settings. Omitted values inherit
from [`SmallOSConfig.client_defaults`](configuration.md) when the client is
attached to a task. Unix TLS supports custom CA and client certificate paths.

For complete constructor options, protocol behavior, and examples, read the
[client reference](../SmallPackage/clients/README.md).
