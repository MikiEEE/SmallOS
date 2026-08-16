"""
Platform kernels for smallOS.

The scheduler is intentionally written against a tiny interface so the runtime
can stay portable across desktop Python and MicroPython boards. This module
keeps the shared surface in one place, then layers a few practical profiles on
top:
- ``Unix`` for desktop development and testing
- ``MicroPythonKernel`` for the generic portable subset of MicroPython
- thin board profiles like ``ESP32`` and ``PicoW`` for board-flavored defaults

The important design choice is that board profiles do not own scheduling logic.
They only provide capability hints and convenience configuration around the
shared MicroPython transport/time API.
"""

from __future__ import annotations

try:
	from typing import TYPE_CHECKING
except ImportError:  # pragma: no cover - exercised on constrained runtimes
	TYPE_CHECKING = False

if TYPE_CHECKING:
	from collections.abc import Iterable, Mapping, Sequence
	from typing import Any, cast


_UNSET = object()


def _import_first(*module_names: str) -> Any | None:
	"""
	Import the first available module name from a list.

	This keeps the rest of the kernel code readable when we want CPython and
	MicroPython fallbacks like ``time``/``utime`` or ``socket``/``usocket``.
	"""
	for module_name in module_names:
		if not module_name:
			continue
		try:
			return __import__(module_name)
		except ImportError:
			continue
	return None


def _portable_shell_split(line: str) -> list[str]:
	"""
	Tokenize one shell command line without relying on desktop-only helpers.

	This parser is intentionally small but still handles the common cases a
	MicroPython-facing shell needs:
	- whitespace-separated tokens
	- single or double quoted strings
	- backslash escaping for the next character
	"""
	tokens = []
	current = []
	quote = None
	escape = False

	for char in line:
		if escape:
			current.append(char)
			escape = False
			continue

		if char == "\\":
			escape = True
			continue

		if quote is not None:
			if char == quote:
				quote = None
			else:
				current.append(char)
			continue

		if char in ("'", '"'):
			quote = char
			continue

		if char.isspace():
			if current:
				tokens.append("".join(current))
				current = []
			continue

		current.append(char)

	if escape:
		current.append("\\")

	if quote is not None:
		raise ValueError("unterminated quoted string")

	if current:
		tokens.append("".join(current))
	return tokens


def _io_wait_lookup_key(obj):
	"""Return the stable descriptor/key used by poll-style backends."""
	if hasattr(obj, 'fileno'):
		try:
			return obj.fileno()
		except Exception:
			pass
	return obj


class _SelectorIOWaitSet:
	"""Persistent CPython selector with delta-updated registrations."""

	def __init__(self, selector, read_mask, write_mask):
		self._selector = selector
		self._read_mask = read_mask
		self._write_mask = write_mask
		self._entries = {}
		self._objects_by_key = {}
		self._closed = False

	def _event_mask(self, readable, writable):
		mask = 0
		if readable:
			mask |= self._read_mask
		if writable:
			mask |= self._write_mask
		return mask

	def _remove(self, obj):
		entry = self._entries.pop(obj, None)
		if entry is None:
			return
		_, key = entry
		if self._objects_by_key.get(key) is obj:
			del self._objects_by_key[key]
		try:
			self._selector.unregister(key)
		except (KeyError, OSError, ValueError):
			# The descriptor may already have been closed and removed by the OS.
			pass

	def _discard_stale_key_owner(self, obj, key):
		existing_obj = self._objects_by_key.get(key)
		if existing_obj is None or existing_obj is obj:
			return

		if _io_wait_lookup_key(existing_obj) == key:
			raise ValueError(
				'I/O descriptor {} is already registered by another object.'.format(key)
			)
		self._remove(existing_obj)

	def set_interest(self, obj, readable, writable):
		"""Apply one object's combined read/write interest when it changes."""
		if self._closed:
			raise RuntimeError('I/O wait set is closed.')

		mask = self._event_mask(readable, writable)
		entry = self._entries.get(obj)
		if entry is None:
			if mask == 0:
				return
			lookup_key = _io_wait_lookup_key(obj)
			self._discard_stale_key_owner(obj, lookup_key)
			selector_key = self._selector.register(obj, mask, obj)
			key = selector_key.fd
			self._entries[obj] = (mask, key)
			self._objects_by_key[key] = obj
			return

		old_mask, key = entry
		if mask == 0:
			self._remove(obj)
			return
		if mask == old_mask:
			return

		current_key = _io_wait_lookup_key(obj)
		if current_key != key:
			self._remove(obj)
			self.set_interest(obj, readable, writable)
			return

		self._selector.modify(key, mask, obj)
		self._entries[obj] = (mask, key)

	def wait(self, timeout_ms=None):
		"""Wait for readiness without rebuilding the registered descriptor set."""
		if self._closed:
			raise RuntimeError('I/O wait set is closed.')
		timeout = None if timeout_ms is None else max(0, timeout_ms) / 1000
		events = self._selector.select(timeout)
		ready_read = []
		ready_write = []
		for selector_key, mask in events:
			obj = selector_key.data
			entry = self._entries.get(obj)
			if entry is None or entry[1] != selector_key.fd:
				raise RuntimeError('I/O selector returned a stale readiness event.')
			if mask & self._read_mask:
				ready_read.append(obj)
			if mask & self._write_mask:
				ready_write.append(obj)
		return ready_read, ready_write

	def close(self):
		"""Release selector resources without closing registered user objects."""
		if self._closed:
			return
		for obj in list(self._entries):
			self._remove(obj)
		self._selector.close()
		self._closed = True


class _PollIOWaitSet:
	"""Portable persistent poll set used by MicroPython kernels."""

	def __init__(self, select_mod, poller):
		self._poller = poller
		self._read_mask = getattr(select_mod, 'POLLIN', 0x001)
		self._write_mask = getattr(select_mod, 'POLLOUT', 0x004)
		self._invalid_mask = getattr(select_mod, 'POLLNVAL', 0x020)
		self._error_mask = (
			getattr(select_mod, 'POLLERR', 0x008)
			| getattr(select_mod, 'POLLHUP', 0x010)
			| getattr(select_mod, 'POLLRDHUP', 0)
			| self._invalid_mask
		)
		self._entries = {}
		self._objects_by_key = {}
		self._closed = False

	def _event_mask(self, readable, writable):
		mask = 0
		if readable:
			mask |= self._read_mask
		if writable:
			mask |= self._write_mask
		return mask

	def _remove(self, obj):
		entry = self._entries.pop(obj, None)
		if entry is None:
			return
		_, key = entry
		if self._objects_by_key.get(key) is obj:
			del self._objects_by_key[key]

		try:
			self._poller.unregister(obj)
			return
		except Exception:
			pass
		try:
			self._poller.unregister(key)
		except Exception:
			# Some MicroPython ports discard closed streams automatically.
			pass

	def _discard_stale_key_owner(self, obj, key):
		existing_obj = self._objects_by_key.get(key)
		if existing_obj is None or existing_obj is obj:
			return
		if _io_wait_lookup_key(existing_obj) == key:
			raise ValueError(
				'I/O descriptor {} is already registered by another object.'.format(key)
			)
		self._remove(existing_obj)

	def set_interest(self, obj, readable, writable):
		"""Apply one poll registration delta."""
		if self._closed:
			raise RuntimeError('I/O wait set is closed.')

		mask = self._event_mask(readable, writable)
		entry = self._entries.get(obj)
		if entry is None:
			if mask == 0:
				return
			key = _io_wait_lookup_key(obj)
			self._discard_stale_key_owner(obj, key)
			self._poller.register(obj, mask)
			self._entries[obj] = (mask, key)
			self._objects_by_key[key] = obj
			return

		old_mask, key = entry
		if mask == 0:
			self._remove(obj)
			return
		if mask == old_mask:
			return

		current_key = _io_wait_lookup_key(obj)
		if current_key != key:
			self._remove(obj)
			self.set_interest(obj, readable, writable)
			return

		modifier = getattr(self._poller, 'modify', None)
		if modifier is not None:
			modifier(obj, mask)
		else:
			# MicroPython permits repeated register() calls to update the mask.
			self._poller.register(obj, mask)
		self._entries[obj] = (mask, key)

	def _ready_object(self, event_obj):
		try:
			if event_obj in self._entries:
				return event_obj
		except (KeyError, TypeError):
			pass
		try:
			return self._objects_by_key[event_obj]
		except (KeyError, TypeError):
			raise RuntimeError('poll returned an unknown I/O object.')

	def wait(self, timeout_ms=None):
		"""Consume poll/ipoll events immediately and return original objects."""
		if self._closed:
			raise RuntimeError('I/O wait set is closed.')
		timeout = -1 if timeout_ms is None else max(0, int(timeout_ms))
		ipoll = getattr(self._poller, 'ipoll', None)
		events = ipoll(timeout) if callable(ipoll) else self._poller.poll(timeout)
		if TYPE_CHECKING:
			# MicroPython pollers return iterable (object, mask) event records,
			# but their dynamic API cannot express that to Pyright.
			events = cast("Iterable[Sequence[Any]]", events)

		ready_read = []
		ready_write = []
		for event in events:
			event_obj = event[0]
			mask = event[1]
			obj = self._ready_object(event_obj)
			entry = self._entries.get(obj)
			if entry is None:
				raise RuntimeError('poll returned a stale readiness event.')
			requested_mask = entry[0]
			ready_mask = mask
			if mask & self._error_mask:
				# HUP/ERR apply to the requested directions even though callers do
				# not include those unsolicited bits in the registration mask.
				ready_mask |= requested_mask
			if ready_mask & self._read_mask:
				ready_read.append(obj)
			if ready_mask & self._write_mask:
				ready_write.append(obj)
			if mask & self._invalid_mask:
				self._remove(obj)
		return ready_read, ready_write

	def close(self):
		"""Unregister streams and clear constrained-runtime references."""
		if self._closed:
			return
		for obj in list(self._entries):
			self._remove(obj)
		closer = getattr(self._poller, 'close', None)
		if closer is not None:
			closer()
		self._objects_by_key.clear()
		self._closed = True


def detect_micropython_machine_name(sys_mod: Any = None, os_mod: Any = None) -> str:
	"""
	Best-effort lookup of the active board/firmware machine name.

	MicroPython commonly exposes a descriptive string through
	``sys.implementation._machine``. When that is unavailable we fall back to
	``os.uname().machine``.
	"""
	if sys_mod is None:
		sys_mod = _import_first('sys')

	if sys_mod is not None:
		implementation = getattr(sys_mod, 'implementation', None)
		machine_name = getattr(implementation, '_machine', None)
		if machine_name:
			return machine_name

	if os_mod is None:
		os_mod = _import_first('os')

	if os_mod is not None and hasattr(os_mod, 'uname'):
		try:
			uname_result = os_mod.uname()
		except TypeError:
			uname_result = os_mod.uname
		machine_name = getattr(uname_result, 'machine', None)
		if machine_name:
			return machine_name

	return ''


def build_micropython_kernel(
	machine_name: str | None = None, **kwargs: Any
) -> MicroPythonKernel:
	"""
	Return the best built-in MicroPython kernel profile for the current board.

	This helper is intentionally conservative: it only selects a board-specific
	profile when the firmware string clearly identifies one of the built-in board
	targets. Everything else falls back to the generic ``MicroPythonKernel``.
	"""
	name = (machine_name or detect_micropython_machine_name() or '').lower()

	if 'pico w' in name or 'pico 2 w' in name:
		return PicoW(**kwargs)
	if 'esp32' in name:
		return ESP32(**kwargs)
	if 'esp8266' in name:
		return ESP8266(**kwargs)
	return MicroPythonKernel(**kwargs)


class Kernel:
	'''
	@class Kernel - Soft interface for the platform layer.

	The runtime keeps this surface intentionally small:
	- text output
	- wall-clock time when available
	- scheduler timing built on ticks-style APIs
	- sleeping and I/O readiness waiting
	- generic TCP/TLS stream primitives

	Higher-level protocols such as HTTPS, Redis, MQTT, RabbitMQ/AMQP, and Kafka
	should be built in userland on top of these generic facilities instead of
	requiring protocol-specific kernel methods.
	'''

	def __init__(self) -> None:
		self._scheduler_anchor_tick = None
		self._scheduler_elapsed_ms = 0

	def write(self, msg: str) -> None:
		pass

	def shell_split(self, line: str) -> list[str]:
		"""
		Tokenize one shell command line.

		The base implementation uses a small portable parser so shells can work on
		platforms where ``shlex`` is unavailable. Desktop kernels may override
		this with richer parsing behavior.
		"""
		return _portable_shell_split(line)

	def time_epoch(self) -> float:
		raise NotImplementedError

	def ticks_ms(self) -> int:
		raise NotImplementedError

	def ticks_add(self, base: int, delta_ms: int) -> int:
		return base + delta_ms

	def ticks_diff(self, end: int, start: int) -> int:
		return end - start

	def time_monotonic(self) -> float:
		return self.scheduler_now_ms() / 1000

	def scheduler_now_ms(self) -> int:
		'''
		Returns a non-decreasing scheduler clock in milliseconds.

		On MicroPython this is derived from ticks_ms/ticks_diff so wrap-around is
		hidden from the scheduler and queue code.
		'''
		current = self.ticks_ms()
		if self._scheduler_anchor_tick is None:
			self._scheduler_anchor_tick = current
			return self._scheduler_elapsed_ms

		delta = self.ticks_diff(current, self._scheduler_anchor_tick)
		if delta < 0:
			delta = 0
		self._scheduler_elapsed_ms += delta
		self._scheduler_anchor_tick = current
		return self._scheduler_elapsed_ms

	def sleep(self, secs: float) -> None:
		self.sleep_ms(int(max(0, secs) * 1000))
		return

	def sleep_ms(self, delay_ms: int) -> None:
		pass

	def io_wait(
		self,
		readables: Iterable[Any],
		writables: Iterable[Any],
		timeout_ms: int | None = None,
	) -> tuple[list[Any], list[Any]]:
		return [], []

	def create_io_wait_set(self):
		"""Return an optional persistent readiness set for one scheduler run."""
		return None

	def supports_external_wait_objects(self) -> bool:
		"""Whether ``io_wait`` can wake on adapter-owned readiness objects."""
		return False

	def validate_io_wait_object(
		self, obj: Any
	) -> tuple[bool, BaseException | None]:
		"""
		Return whether ``obj`` still looks safe to hand to poll/select.

		Closed sockets on CPython typically report ``fileno() == -1`` after close.
		Letting those reach ``select.poll().register(...)`` crashes the runtime
		with ``ValueError`` before the waiting task can be resumed or cleaned up.
		"""
		if obj is None:
			return False, ValueError('I/O wait object cannot be None.')
		if isinstance(obj, int):
			if obj < 0:
				return False, ValueError(
					'I/O wait object has invalid file descriptor ({}).'.format(obj)
				)
			return True, None
		if hasattr(obj, 'fileno'):
			try:
				fd = obj.fileno()
			except Exception as exc:
				return False, exc
			if isinstance(fd, int) and fd < 0:
				return False, ValueError(
					'I/O wait object has invalid file descriptor ({}).'.format(fd)
				)
		return True, None

	def resolve_address(self, host: str, port: int) -> Any:
		return None

	def socket_open(self, address_info: Any) -> Any:
		return None

	def socket_setblocking(self, sock: Any, flag: bool) -> None:
		return

	def socket_connect(self, sock: Any, sockaddr: Any) -> bool:
		return True

	def socket_connection_error(self, sock: Any) -> int:
		return 0

	def socket_send(self, sock: Any, data: bytes) -> int:
		return 0

	def socket_recv(self, sock: Any, buffer_size: int) -> bytes:
		return b''

	def socket_close(self, sock: Any) -> None:
		return

	def socket_wrap_tls_client(
		self,
		sock,
		server_hostname=None,
		tls_ca_file=None,
		tls_cert_file=None,
		tls_key_file=None,
		tls_verify=True,
	):
		return sock

	def socket_do_handshake(self, sock: Any) -> None:
		return

	def _extract_errno(self, exc: BaseException) -> int | None:
		errno_value = getattr(exc, 'errno', None)
		if errno_value is not None:
			return errno_value
		if getattr(exc, 'args', None):
			return exc.args[0]
		return None

	def socket_needs_read(self, exc: BaseException) -> bool:
		return isinstance(exc, BlockingIOError)

	def socket_needs_write(self, exc: BaseException) -> bool:
		return False

	def _poll_lookup_key(self, obj: Any) -> Any:
		"""
		Return the identity key used to map poll events back to registered objects.

		``select.poll()`` typically reports integer file descriptors instead of the
		original socket object, so the kernel needs a stable way to translate poll
		results back into the scheduler's waiter keys.
		"""
		return _io_wait_lookup_key(obj)


class Unix(Kernel):
	'''
	For Unix-like systems.

	The imports used by this implementation are loaded here instead of at module
	import time so alternate kernels can import ``Kernel.py`` without requiring
	desktop-oriented modules such as ``select`` and ``socket`` to exist.
	'''

	def __init__(self):
		super().__init__()
		import errno
		import os
		import shlex
		import select
		import selectors
		import socket
		import ssl
		import sys
		import time

		self._errno = errno
		self._os = os
		self._shlex = shlex
		self._select = select
		self._selector_factory = selectors.DefaultSelector
		if sys.platform == 'darwin' and hasattr(selectors, 'PollSelector'):
			# Kqueue has a comparatively high fixed cost for zero-time checks on
			# macOS. Persistent poll avoids the small-wait-set scheduler regression
			# while still removing registration rebuilds.
			self._selector_factory = selectors.PollSelector
		self._selector_read_mask = selectors.EVENT_READ
		self._selector_write_mask = selectors.EVENT_WRITE
		self._socket = socket
		self._ssl = ssl
		self._sys = sys
		self._time = time
		self._poll_factory = getattr(select, 'poll', None)
		return

	def write(self, msg):
		self._sys.stdout.write(msg)
		self._sys.stdout.flush()
		return

	def shell_split(self, line):
		"""Use ``shlex`` on Unix for richer desktop-style shell parsing."""
		return self._shlex.split(line)

	def time_epoch(self):
		return self._time.time()

	def ticks_ms(self):
		return int(self._time.monotonic() * 1000)

	def ticks_add(self, base, delta_ms):
		return base + delta_ms

	def ticks_diff(self, end, start):
		return end - start

	def time_monotonic(self):
		return self._time.monotonic()

	def sleep_ms(self, delay_ms):
		self._time.sleep(max(0, delay_ms) / 1000)
		return

	def io_wait(self, readables, writables, timeout_ms=None):
		if self._poll_factory:
			poller = self._poll_factory()
			mask_by_object = {}
			object_by_key = {}
			read_mask = getattr(self._select, 'POLLIN', 0x001)
			write_mask = getattr(self._select, 'POLLOUT', 0x004)

			for obj in readables:
				mask_by_object[obj] = mask_by_object.get(obj, 0) | read_mask
			for obj in writables:
				mask_by_object[obj] = mask_by_object.get(obj, 0) | write_mask

			for obj, mask in mask_by_object.items():
				object_by_key[self._poll_lookup_key(obj)] = obj
				poller.register(obj, mask)

			timeout = -1 if timeout_ms is None else max(0, int(timeout_ms))
			events = poller.poll(timeout)

			ready_read = []
			ready_write = []
			for obj, mask in events:
				ready_obj = object_by_key.get(obj, obj)
				if mask & read_mask:
					ready_read.append(ready_obj)
				if mask & write_mask:
					ready_write.append(ready_obj)
			return ready_read, ready_write

		timeout = None if timeout_ms is None else max(0, timeout_ms) / 1000
		if not readables and not writables:
			if timeout is not None and timeout > 0:
				self._time.sleep(timeout)
			return [], []
		ready_read, ready_write, _ = self._select.select(readables, writables, [], timeout)
		return ready_read, ready_write

	def create_io_wait_set(self):
		"""Create the runtime-owned selector used for persistent Unix waits."""
		return _SelectorIOWaitSet(
			self._selector_factory(),
			self._selector_read_mask,
			self._selector_write_mask,
		)

	def validate_io_wait_object(self, obj: Any) -> tuple[bool, BaseException | None]:
		"""Reject Unix descriptors that were closed behind a persistent wait set."""
		is_valid, exc = super().validate_io_wait_object(obj)
		if not is_valid:
			return is_valid, exc

		fd = _io_wait_lookup_key(obj)
		if not isinstance(fd, int):
			return True, None
		try:
			self._os.fstat(fd)
		except (OSError, OverflowError, ValueError) as exc:
			return False, exc
		return True, None

	def supports_external_wait_objects(self) -> bool:
		return True

	def resolve_address(self, host, port):
		return self._socket.getaddrinfo(host, port, type=self._socket.SOCK_STREAM)[0]

	def socket_open(self, address_info):
		family, socktype, proto, _, _ = address_info
		return self._socket.socket(family, socktype, proto)

	def socket_setblocking(self, sock, flag):
		sock.setblocking(flag)
		return

	def socket_connect(self, sock, sockaddr):
		err = sock.connect_ex(sockaddr)
		pending = {
			0,
			getattr(self._errno, 'EINPROGRESS', 0),
			getattr(self._errno, 'EWOULDBLOCK', 0),
			getattr(self._errno, 'EALREADY', 0),
			getattr(self._errno, 'EINTR', 0),
			getattr(self._errno, 'EISCONN', 0),
		}
		if err == 0:
			return True
		if err in pending:
			return False
		raise OSError(err, 'socket connect failed')

	def socket_connection_error(self, sock):
		return sock.getsockopt(self._socket.SOL_SOCKET, self._socket.SO_ERROR)

	def socket_send(self, sock, data):
		return sock.send(data)

	def socket_recv(self, sock, buffer_size):
		return sock.recv(buffer_size)

	def socket_close(self, sock):
		sock.close()
		return

	def socket_wrap_tls_client(
		self,
		sock,
		server_hostname=None,
		tls_ca_file=None,
		tls_cert_file=None,
		tls_key_file=None,
		tls_verify=True,
	):
		if tls_verify:
			context = self._ssl.create_default_context(cafile=tls_ca_file)
		else:
			context = self._ssl.SSLContext(self._ssl.PROTOCOL_TLS_CLIENT)
			context.check_hostname = False
			context.verify_mode = self._ssl.CERT_NONE
		if tls_cert_file is not None:
			context.load_cert_chain(certfile=tls_cert_file, keyfile=tls_key_file)
		wrapped = context.wrap_socket(
			sock,
			server_hostname=server_hostname,
			do_handshake_on_connect=False,
		)
		wrapped.setblocking(False)
		return wrapped

	def socket_do_handshake(self, sock):
		sock.do_handshake()
		return

	def socket_needs_read(self, exc):
		return isinstance(exc, (BlockingIOError, self._ssl.SSLWantReadError))

	def socket_needs_write(self, exc):
		return isinstance(exc, self._ssl.SSLWantWriteError)


class MicroPythonKernel(Kernel):
	'''
	Generic kernel targeting the portable subset of MicroPython.

	This class is meant to cover most MicroPython ports without requiring one
	kernel class per board. When board-specific differences appear, prefer small
	subclasses or configuration helpers over full kernel rewrites.
	'''

	def __init__(
		self,
		network_interface=None,
		board_name='Generic MicroPython',
		wifi_country=None,
		wifi_hostname=None,
		wifi_power_management=None,
		modules=None,
	):
		super().__init__()

		modules = modules or {}

		time_mod = modules.get('time') or _import_first('time', 'utime')
		if time_mod is None:
			raise ImportError('MicroPythonKernel requires time or utime.')
		self._time = time_mod
		self._select = modules.get('select') or _import_first('select', 'uselect')
		socket_mod = modules.get('socket') or _import_first('socket', 'usocket')
		if socket_mod is None:
			raise ImportError('MicroPythonKernel requires socket or usocket.')
		self._socket = socket_mod
		self._ssl = modules.get('ssl')
		if self._ssl is None:
			self._ssl = _import_first('ssl', 'ussl')
		self._sys = modules.get('sys') or _import_first('sys')
		self._os = modules.get('os') or _import_first('os')
		self._network = modules.get('network') or _import_first('network')
		self._rp2 = modules.get('rp2') or _import_first('rp2')
		self._machine = modules.get('machine') or _import_first('machine')
		self._poll_factory = getattr(self._select, 'poll', None)
		self.network_interface = network_interface
		self.board_name = board_name
		self.default_wifi_country = wifi_country
		self.default_wifi_hostname = wifi_hostname
		self.default_wifi_power_management = wifi_power_management
		return

	def write(self, msg):
		if self._sys and getattr(self._sys, 'stdout', None):
			self._sys.stdout.write(msg)
			return
		print(msg, end='')

	def time_epoch(self):
		if hasattr(self._time, 'time'):
			return self._time.time()
		return 0

	def ticks_ms(self):
		if hasattr(self._time, 'ticks_ms'):
			return self._time.ticks_ms()
		return int(self.time_epoch() * 1000)

	def ticks_add(self, base, delta_ms):
		if hasattr(self._time, 'ticks_add'):
			return self._time.ticks_add(base, delta_ms)
		return base + delta_ms

	def ticks_diff(self, end, start):
		if hasattr(self._time, 'ticks_diff'):
			return self._time.ticks_diff(end, start)
		return end - start

	def sleep_ms(self, delay_ms):
		if hasattr(self._time, 'sleep_ms'):
			self._time.sleep_ms(max(0, int(delay_ms)))
			return
		if hasattr(self._time, 'sleep'):
			self._time.sleep(max(0, delay_ms) / 1000)
			return

	def io_wait(self, readables, writables, timeout_ms=None):
		if self._poll_factory:
			poller = self._poll_factory()
			read_mask = getattr(self._select, 'POLLIN', 0x001)
			write_mask = getattr(self._select, 'POLLOUT', 0x004)
			mask_by_object = {}
			object_by_key = {}

			for obj in readables:
				mask_by_object[obj] = mask_by_object.get(obj, 0) | read_mask
			for obj in writables:
				mask_by_object[obj] = mask_by_object.get(obj, 0) | write_mask

			for obj, mask in mask_by_object.items():
				object_by_key[self._poll_lookup_key(obj)] = obj
				poller.register(obj, mask)

			timeout = -1 if timeout_ms is None else max(0, int(timeout_ms))
			events = poller.poll(timeout)

			ready_read = []
			ready_write = []
			for obj, mask in events:
				ready_obj = object_by_key.get(obj, obj)
				if mask & read_mask:
					ready_read.append(ready_obj)
				if mask & write_mask:
					ready_write.append(ready_obj)
			return ready_read, ready_write

		if timeout_ms is not None and timeout_ms > 0:
			self.sleep_ms(timeout_ms)
		return [], []

	def create_io_wait_set(self):
		"""Reuse one poller when the active MicroPython port supplies it."""
		if self._poll_factory is None:
			return None
		return _PollIOWaitSet(self._select, self._poll_factory())

	def supports_external_wait_objects(self) -> bool:
		return bool(self._poll_factory)

	def resolve_address(self, host, port):
		return self._socket.getaddrinfo(host, port)[0]

	def socket_open(self, address_info):
		family, socktype, proto, _, _ = address_info
		return self._socket.socket(family, socktype, proto)

	def socket_setblocking(self, sock, flag):
		sock.setblocking(flag)
		return

	def socket_connect(self, sock, sockaddr):
		try:
			sock.connect(sockaddr)
			return True
		except Exception as exc:
			err = self._extract_errno(exc)
			# 115 = EINPROGRESS, 11 = EAGAIN on most MicroPython targets
			pending = {
				115, 11,
			}
			if err in pending or self.socket_needs_read(exc) or self.socket_needs_write(exc):
				return False
			raise

	def socket_connection_error(self, sock):
		sol_socket = getattr(self._socket, 'SOL_SOCKET', 1)
		so_error = getattr(self._socket, 'SO_ERROR', 4)
		return sock.getsockopt(sol_socket, so_error)

	def socket_send(self, sock, data):
		return sock.send(data)

	def socket_recv(self, sock, buffer_size):
		return sock.recv(buffer_size)

	def socket_close(self, sock):
		sock.close()
		return

	def socket_wrap_tls_client(
		self,
		sock,
		server_hostname=None,
		tls_ca_file=None,
		tls_cert_file=None,
		tls_key_file=None,
		tls_verify=True,
	):
		if not self._ssl:
			raise NotImplementedError('TLS support is not available on this MicroPython port.')

		kwargs = {}
		if server_hostname is not None:
			kwargs['server_hostname'] = server_hostname
		if tls_cert_file is not None:
			kwargs['cert'] = tls_cert_file
		if tls_key_file is not None:
			kwargs['key'] = tls_key_file
		if not tls_verify and hasattr(self._ssl, 'CERT_NONE'):
			kwargs['cert_reqs'] = self._ssl.CERT_NONE

		# Build a list of progressively simpler kwarg sets to handle ports
		# whose ssl.wrap_socket rejects unknown keyword arguments.  When
		# tls_verify is True we never fall back to a bare call — doing so
		# would silently disable certificate verification.
		attempts = []
		if kwargs:
			attempts.append(kwargs)
		if 'cert' in kwargs or 'key' in kwargs or 'cert_reqs' in kwargs:
			attempts.append({k: v for k, v in kwargs.items() if k == 'server_hostname'})
		if not tls_verify:
			# Only allow the bare fallback when verification is explicitly
			# disabled — falling back here with tls_verify=True would be a
			# silent security downgrade.
			attempts.append({})
		if not attempts:
			attempts.append({})

		last_error = None
		for wrap_kwargs in attempts:
			try:
				wrapped = self._ssl.wrap_socket(sock, **wrap_kwargs)
				break
			except TypeError as exc:
				last_error = exc
		else:
			if last_error is None:
				raise RuntimeError('TLS wrapper did not produce a socket.')
			raise last_error
		if hasattr(wrapped, 'setblocking'):
			wrapped.setblocking(False)
		return wrapped

	def socket_do_handshake(self, sock):
		if hasattr(sock, 'do_handshake'):
			sock.do_handshake()
		return

	def socket_needs_read(self, exc):
		err = self._extract_errno(exc)
		if err in {11, 115}:
			return True
		want_read_error = getattr(self._ssl, 'SSLWantReadError', None)
		if isinstance(want_read_error, type) and isinstance(exc, want_read_error):
			return True
		return isinstance(exc, BlockingIOError)

	def socket_needs_write(self, exc):
		want_write_error = getattr(self._ssl, 'SSLWantWriteError', None)
		if isinstance(want_write_error, type) and isinstance(exc, want_write_error):
			return True
		return False

	def machine_name(self):
		'''
		Return the current firmware/board descriptor when the platform exposes one.
		'''
		return detect_micropython_machine_name(sys_mod=self._sys, os_mod=self._os)

	def _configure_wifi_country(self, country):
		'''
		Apply a regulatory country code when the port exposes a hook for it.
		'''
		if not country:
			return False

		if self._rp2 and hasattr(self._rp2, 'country'):
			self._rp2.country(country)
			return True

		if self._network and hasattr(self._network, 'country'):
			self._network.country(country)
			return True

		return False

	def _configure_wifi_hostname(self, nic, hostname):
		'''
		Apply a DHCP or stack hostname using whichever API the port exposes.
		'''
		if not hostname:
			return False

		if self._network and hasattr(self._network, 'hostname'):
			self._network.hostname(hostname)
			return True

		if nic and hasattr(nic, 'config'):
			for kwargs in ({'dhcp_hostname': hostname}, {'hostname': hostname}):
				try:
					nic.config(**kwargs)
					return True
				except Exception:
					continue

		return False

	def _configure_wifi_power_management(self, nic, power_management):
		'''
		Apply a board/port-specific Wi-Fi power management mode when supported.
		'''
		if power_management is None or nic is None or not hasattr(nic, 'config'):
			return False

		try:
			nic.config(pm=power_management)
			return True
		except Exception:
			return False

	def prepare_wifi_station(self, nic=None, country=None, hostname=None, power_management=_UNSET):
		'''
		Apply optional board-flavored Wi-Fi configuration before connecting.

		This is the main extension hook used by board profiles. The generic
		implementation stays conservative and only calls settings when the active
		port exposes the needed API.
		'''
		if country is None:
			country = self.default_wifi_country
		if hostname is None:
			hostname = self.default_wifi_hostname
		if power_management is _UNSET:
			power_management = self.default_wifi_power_management

		self._configure_wifi_country(country)
		self._configure_wifi_hostname(nic, hostname)
		self._configure_wifi_power_management(nic, power_management)
		return nic

	def connect_wifi(
		self,
		ssid,
		password,
		timeout_ms=15000,
		country=None,
		hostname=None,
		power_management=_UNSET,
	):
		'''
		Generic helper for ports that expose ``network.WLAN(STA_IF)``.

		Board profiles reuse this method and simply feed in better defaults for the
		target board, which keeps connection workflow shared across ports.
		'''
		if not self._network or not hasattr(self._network, 'WLAN'):
			raise NotImplementedError('This MicroPython port does not expose network.WLAN.')

		nic = self.network_interface
		if nic is None:
			nic = self._network.WLAN(self._network.STA_IF)
			self.network_interface = nic

		nic.active(True)
		self.prepare_wifi_station(
			nic=nic,
			country=country,
			hostname=hostname,
			power_management=power_management,
		)
		if nic.isconnected():
			return nic

		nic.connect(ssid, password)
		start = self.ticks_ms()
		while not nic.isconnected():
			if self.ticks_diff(self.ticks_ms(), start) > timeout_ms:
				raise TimeoutError('Timed out waiting for Wi-Fi connection.')
			self.sleep_ms(100)
		return nic


class ESP32(MicroPythonKernel):
	'''
	Board profile for ESP32-based MicroPython dev boards.

	ESP32 is one of the most common hobbyist MicroPython targets, so this class
	gives it a friendly name and a place for ESP32-specific defaults without
	fragmenting the shared runtime behavior.
	'''

	def __init__(self, network_interface=None, hostname=None, modules=None):
		super().__init__(
			network_interface=network_interface,
			board_name='ESP32',
			wifi_hostname=hostname,
			modules=modules,
		)


class PicoW(MicroPythonKernel):
	'''
	Board profile for Raspberry Pi Pico W and Pico 2 W.

	The main board-specific convenience here is Wi-Fi setup: callers can supply
	a regulatory country code, hostname, and optional power management mode while
	still using the same shared transport API as every other MicroPython port.
	'''

	def __init__(
		self,
		network_interface=None,
		country=None,
		hostname=None,
		power_management=None,
		modules=None,
	):
		super().__init__(
			network_interface=network_interface,
			board_name='Raspberry Pi Pico W',
			wifi_country=country,
			wifi_hostname=hostname,
			wifi_power_management=power_management,
			modules=modules,
		)


class ESP8266(MicroPythonKernel):
	'''
	Compatibility alias kept for the earlier project structure.
	'''

	def __init__(self, network_interface=None, hostname=None, modules=None):
		super().__init__(
			network_interface=network_interface,
			board_name='ESP8266',
			wifi_hostname=hostname,
			modules=modules,
		)


RaspberryPiPicoW = PicoW
