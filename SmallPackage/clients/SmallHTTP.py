"""
SmallOS-native HTTP helpers.

This module gives smallOS tasks a compact, dependency-light HTTP client built
on the same cooperative socket stream used by the Redis and MQTT helpers. The
goal is convenience, not full browser parity:
- HTTP/1.1 requests over plain TCP or TLS
- simple `get` / `post` / `put` / `patch` / `delete` helpers
- query string, form body, and JSON body support
- response parsing for content-length, chunked transfer, and connection-close

The client intentionally closes the transport after each request. That keeps
the implementation easy to reason about and works well for the common
"make one request and keep running other tasks" workflow.
"""

import json

from .SmallStream import SmallStream, StreamClosedError


class HTTPProtocolError(Exception):
    """Raised when the peer sends malformed or unsupported HTTP data."""


def _percent_encode(value):
    """Percent-encode one query-string key or value."""
    if isinstance(value, bytes):
        data = value
    else:
        data = str(value).encode("utf-8")

    safe = b"ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789-._~"
    encoded = []
    for byte in data:
        if byte in safe:
            encoded.append(chr(byte))
        else:
            encoded.append("%{:02X}".format(byte))
    return "".join(encoded)


def _normalize_query_value(value):
    """Convert one query-string value into a string-friendly representation."""
    if isinstance(value, bool):
        return "true" if value else "false"
    if value is None:
        return ""
    return value


def _iter_pairs(value):
    """Return a stable iterable of key/value pairs from common mapping inputs."""
    if value is None:
        return []
    if hasattr(value, "items"):
        return list(value.items())
    return list(value)


def _encode_query(params):
    """Encode a dict-or-pairs structure into a URL query string."""
    parts = []
    for key, value in _iter_pairs(params):
        if isinstance(value, (list, tuple)):
            values = value
        else:
            values = [value]
        for item in values:
            parts.append(
                "{}={}".format(
                    _percent_encode(key),
                    _percent_encode(_normalize_query_value(item)),
                )
            )
    return "&".join(parts)


def _split_header_line(line):
    """Split one raw HTTP header line into name/value pieces."""
    if b":" not in line:
        raise HTTPProtocolError("Malformed HTTP header line.")
    name, value = line.split(b":", 1)
    return (
        name.decode("utf-8", errors="replace").strip(),
        value.decode("utf-8", errors="replace").strip(),
    )


def _parse_base_url(base_url):
    """Parse a compact `http://` or `https://` base URL without asyncio helpers."""
    if "://" not in base_url:
        raise ValueError("base_url must include http:// or https://")

    scheme, remainder = base_url.split("://", 1)
    scheme = scheme.lower()
    if scheme not in ("http", "https"):
        raise ValueError("Only http and https base URLs are supported.")

    if "/" in remainder:
        authority, base_path = remainder.split("/", 1)
        base_path = "/" + base_path
    else:
        authority = remainder
        base_path = ""

    if not authority:
        raise ValueError("base_url must include a host.")

    if "@" in authority:
        authority = authority.rsplit("@", 1)[1]

    if ":" in authority and not authority.startswith("["):
        host, port_text = authority.rsplit(":", 1)
        port = int(port_text)
    else:
        host = authority
        port = 443 if scheme == "https" else 80

    base_path = base_path.split("#", 1)[0]
    return {
        "host": host,
        "port": port,
        "use_tls": scheme == "https",
        "base_path": base_path.rstrip("/"),
    }


class SmallHTTPResponse:
    """Container for one parsed HTTP response."""

    def __init__(self, http_version, status_code, reason, headers, body):
        self.http_version = http_version
        self.status_code = int(status_code)
        self.reason = reason
        self.raw_headers = list(headers)
        self.headers = {}
        for name, value in self.raw_headers:
            self.headers[name.lower()] = value
        self.body = bytes(body)

    @property
    def ok(self):
        """Return `True` for 2xx responses."""
        return 200 <= self.status_code < 300

    def header(self, name, default=None):
        """Return one response header case-insensitively."""
        return self.headers.get(str(name).lower(), default)

    def text(self, encoding=None):
        """Decode the response body into text."""
        if encoding is None:
            content_type = self.header("content-type", "")
            encoding = "utf-8"
            if "charset=" in content_type:
                encoding = content_type.split("charset=", 1)[1].split(";", 1)[0].strip()
        return self.body.decode(encoding, errors="replace")

    def json(self):
        """Decode the response body as JSON."""
        return json.loads(self.text())


class SmallHTTPClient:
    """
    Minimal cooperative HTTP client for smallOS tasks.

    Typical usage:
    - bind the client to a `base_url`
    - make one or more requests with `await client.get(...)` or `await client.post(...)`
    - inspect `status_code`, `headers`, `body`, `text()`, or `json()`

    The client closes each request stream after reading the response, which
    keeps the behavior predictable on both desktop Python and future embedded
    targets.
    """

    def __init__(
        self,
        task,
        base_url=None,
        host=None,
        port=None,
        use_tls=False,
        server_hostname=None,
        default_headers=None,
        tls_ca_file=None,
        tls_cert_file=None,
        tls_key_file=None,
        tls_verify=True,
    ):
        self.task = task
        self.default_headers = dict(default_headers or {})
        self.tls_ca_file = tls_ca_file
        self.tls_cert_file = tls_cert_file
        self.tls_key_file = tls_key_file
        self.tls_verify = tls_verify
        self.base_path = ""

        if base_url is not None:
            parsed = _parse_base_url(base_url)
            host = parsed["host"]
            port = parsed["port"]
            use_tls = parsed["use_tls"]
            self.base_path = parsed["base_path"]

        if host is None:
            raise ValueError("SmallHTTPClient requires either host=... or base_url=...")

        self.host = host
        self.use_tls = bool(use_tls)
        self.port = int(port or (443 if self.use_tls else 80))
        self.server_hostname = server_hostname or self.host

    def _make_stream(self):
        """Build a fresh transport for one request."""
        return SmallStream(
            self.task,
            host=self.host,
            port=self.port,
            use_tls=self.use_tls,
            server_hostname=self.server_hostname,
            tls_ca_file=self.tls_ca_file,
            tls_cert_file=self.tls_cert_file,
            tls_key_file=self.tls_key_file,
            tls_verify=self.tls_verify,
        )

    def _default_port(self):
        """Return the conventional port for the current scheme."""
        return 443 if self.use_tls else 80

    def _host_header(self):
        """Return the value for the HTTP Host header."""
        if self.port == self._default_port():
            return self.host
        return "{}:{}".format(self.host, self.port)

    def _build_target(self, path, params=None):
        """Build the request target path plus optional query string."""
        path = (path or "").split("#", 1)[0]

        if path.startswith("/"):
            target = path
        elif path:
            prefix = self.base_path.rstrip("/")
            if prefix:
                target = prefix + "/" + path.lstrip("/")
            else:
                target = "/" + path.lstrip("/")
        elif self.base_path:
            target = self.base_path or "/"
        else:
            target = "/"

        if "?" in target:
            path_only, existing_query = target.split("?", 1)
        else:
            path_only = target
            existing_query = ""

        extra_query = _encode_query(params)
        if existing_query and extra_query:
            return "{}?{}&{}".format(path_only, existing_query, extra_query)
        if existing_query:
            return "{}?{}".format(path_only, existing_query)
        if extra_query:
            return "{}?{}".format(path_only, extra_query)
        return path_only

    @staticmethod
    def _set_header(headers, name, value):
        """Set or replace a header case-insensitively while preserving order."""
        for index, (header_name, _) in enumerate(headers):
            if header_name.lower() == name.lower():
                headers[index] = (name, value)
                return
        headers.append((name, value))

    @staticmethod
    def _ensure_header(headers, name, value):
        """Set a header only when the caller has not already provided one."""
        for header_name, _ in headers:
            if header_name.lower() == name.lower():
                return
        headers.append((name, value))

    def _prepare_body(self, data=None, json_body=None, headers=None):
        """Normalize outgoing request body bytes and matching headers."""
        if data is not None and json_body is not None:
            raise ValueError("Pass either data=... or json_body=..., not both.")

        body = b""
        if json_body is not None:
            body = json.dumps(json_body, separators=(",", ":")).encode("utf-8")
            self._set_header(headers, "Content-Type", "application/json")
        elif data is None:
            body = b""
        elif isinstance(data, bytes):
            body = data
        elif isinstance(data, bytearray):
            body = bytes(data)
        elif isinstance(data, memoryview):
            body = bytes(data)
        elif isinstance(data, str):
            body = data.encode("utf-8")
        else:
            body = _encode_query(data).encode("utf-8")
            self._set_header(headers, "Content-Type", "application/x-www-form-urlencoded")
        return body

    async def request(self, method, path="", headers=None, params=None, data=None, json_body=None):
        """Send one HTTP request and return a parsed response object."""
        request_headers = []
        for name, value in self.default_headers.items():
            request_headers.append((str(name), str(value)))
        for name, value in dict(headers or {}).items():
            self._set_header(request_headers, str(name), str(value))

        body = self._prepare_body(data=data, json_body=json_body, headers=request_headers)
        target = self._build_target(path, params=params)

        self._set_header(request_headers, "Host", self._host_header())
        self._ensure_header(request_headers, "User-Agent", "smallOS/0.1")
        self._ensure_header(request_headers, "Accept", "*/*")
        self._ensure_header(request_headers, "Connection", "close")
        if body:
            self._set_header(request_headers, "Content-Length", str(len(body)))

        lines = ["{} {} HTTP/1.1".format(method.upper(), target)]
        for name, value in request_headers:
            lines.append("{}: {}".format(name, value))
        request_bytes = ("\r\n".join(lines) + "\r\n\r\n").encode("utf-8") + body

        stream = self._make_stream()
        try:
            await stream.connect()
            await stream.send_all(request_bytes)
            return await self._read_response(stream, method=method)
        finally:
            stream.close()

    async def get(self, path="", headers=None, params=None):
        """Convenience wrapper for `GET`."""
        return await self.request("GET", path=path, headers=headers, params=params)

    async def post(self, path="", headers=None, params=None, data=None, json_body=None):
        """Convenience wrapper for `POST`."""
        return await self.request("POST", path=path, headers=headers, params=params, data=data, json_body=json_body)

    async def put(self, path="", headers=None, params=None, data=None, json_body=None):
        """Convenience wrapper for `PUT`."""
        return await self.request("PUT", path=path, headers=headers, params=params, data=data, json_body=json_body)

    async def patch(self, path="", headers=None, params=None, data=None, json_body=None):
        """Convenience wrapper for `PATCH`."""
        return await self.request("PATCH", path=path, headers=headers, params=params, data=data, json_body=json_body)

    async def delete(self, path="", headers=None, params=None):
        """Convenience wrapper for `DELETE`."""
        return await self.request("DELETE", path=path, headers=headers, params=params)

    async def _read_response(self, stream, method):
        """Parse one HTTP response from the stream."""
        status_line = (await stream.read_until(b"\r\n"))[:-2].decode("utf-8", errors="replace")
        parts = status_line.split(" ", 2)
        if len(parts) < 2 or not parts[0].startswith("HTTP/"):
            raise HTTPProtocolError("Malformed HTTP status line.")

        http_version = parts[0]
        status_code = int(parts[1])
        reason = parts[2] if len(parts) > 2 else ""

        headers = []
        while True:
            line = await stream.read_until(b"\r\n")
            if line == b"\r\n":
                break
            headers.append(_split_header_line(line[:-2]))

        header_map = {name.lower(): value for name, value in headers}
        method = str(method).upper()

        if method == "HEAD" or status_code in (204, 304) or 100 <= status_code < 200:
            body = b""
        elif "chunked" in header_map.get("transfer-encoding", "").lower():
            body = await self._read_chunked_body(stream)
        elif "content-length" in header_map:
            body = await stream.read_exactly(int(header_map["content-length"]))
        else:
            body = await self._read_to_close(stream)

        return SmallHTTPResponse(
            http_version=http_version,
            status_code=status_code,
            reason=reason,
            headers=headers,
            body=body,
        )

    async def _read_chunked_body(self, stream):
        """Read an HTTP chunked-transfer body."""
        chunks = []
        while True:
            line = (await stream.read_until(b"\r\n"))[:-2]
            size_text = line.split(b";", 1)[0]
            chunk_size = int(size_text.decode("ascii"), 16)
            if chunk_size == 0:
                while True:
                    trailer = await stream.read_until(b"\r\n")
                    if trailer == b"\r\n":
                        return b"".join(chunks)
            chunks.append(await stream.read_exactly(chunk_size))
            trailer = await stream.read_exactly(2)
            if trailer != b"\r\n":
                raise HTTPProtocolError("Malformed chunk terminator.")

    async def _read_to_close(self, stream):
        """Read until the peer closes the HTTP stream."""
        chunks = []
        while True:
            try:
                chunks.append(await stream.recv_some())
            except StreamClosedError:
                return b"".join(chunks)
