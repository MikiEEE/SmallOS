# Configuration

[Previous: Task lifecycle](task-lifecycle.md) · [Guide home](README.md) ·
[Next: API reference](api-reference.md)

The runtime uses `SmallOSConfig`, which can be constructed directly or loaded
from [`smallos.config.json`](../smallos.config.json).

```python
from SmallPackage import SmallOS, SmallOSConfig

config = SmallOSConfig.from_json_file("smallos.config.json")
runtime = SmallOS(config=config)
```

## Fields

- `task_capacity`: maximum tracked tasks and PID slots
- `priority_levels`: number of ready-queue categories
- `io_buffer_length`: buffered application output retained when terminal view
  is hidden
- `eternal_watchers`: whether watcher-only work keeps the runtime alive
- `client_defaults`: shared stream and protocol-client limits

Example:

```json
{
  "task_capacity": 1024,
  "priority_levels": 10,
  "io_buffer_length": 1024,
  "eternal_watchers": false,
  "client_defaults": {
    "stream": {
      "max_buffer_size": 16777216
    },
    "http": {
      "max_response_size": 16777216
    },
    "redis": {
      "max_response_size": 16777216,
      "max_nesting_depth": 32
    },
    "mqtt": {
      "keepalive": 60,
      "max_packet_size": 262144,
      "max_queued_messages": 1024
    },
    "sse": {
      "max_event_size": 1048576,
      "max_line_size": 65536
    },
    "websocket": {
      "max_frame_size": 1048576,
      "max_message_size": 4194304,
      "max_line_size": 16384
    }
  }
}
```

The loader also accepts `oslist_length` as an alias for `task_capacity` and
`num_categories` as an alias for `priority_levels` so older experiments can
map onto the current runtime.

Client constructors accept explicit overrides. When a client is created from
an attached task, omitted values inherit from `task.OS.config`.
