import sys
import unittest

sys.path.append("..")

from SmallPackage.Kernel import Kernel
from SmallPackage.clients import SmallMQTTClient
from SmallPackage.SmallOS import SmallOS
from SmallPackage.clients import SmallRedisClient
from SmallPackage.SmallTask import SmallTask


class ScriptedSocket:
    def __init__(self, recv_chunks=None):
        self.recv_chunks = [bytes(chunk) for chunk in (recv_chunks or [])]
        self.sent = []
        self.closed = False
        self.blocking = True


class ScriptedKernel(Kernel):
    def __init__(self, sockets):
        super().__init__()
        self.now = 0
        self.output = []
        self.sockets = list(sockets)
        self.opened = []

    def write(self, msg):
        self.output.append(msg)

    def time_epoch(self):
        return self.now / 1000

    def time_monotonic(self):
        return self.now / 1000

    def ticks_ms(self):
        return self.now

    def ticks_add(self, base, delta_ms):
        return base + delta_ms

    def ticks_diff(self, end, start):
        return end - start

    def sleep_ms(self, delay_ms):
        if delay_ms > 0:
            self.now += int(delay_ms)

    def io_wait(self, readables, writables, timeout_ms=None):
        ready_read = [obj for obj in readables if obj.recv_chunks]
        ready_write = list(writables)
        if timeout_ms is not None and timeout_ms > 0 and not ready_read and not ready_write:
            self.now += int(timeout_ms)
        return ready_read, ready_write

    def resolve_address(self, host, port):
        return (0, 0, 0, "", (host, port))

    def socket_open(self, address_info):
        sock = self.sockets.pop(0)
        self.opened.append(sock)
        return sock

    def socket_setblocking(self, sock, flag):
        sock.blocking = flag

    def socket_connect(self, sock, sockaddr):
        return False

    def socket_connection_error(self, sock):
        return 0

    def socket_send(self, sock, data):
        payload = bytes(data)
        sock.sent.append(payload)
        return len(payload)

    def socket_recv(self, sock, buffer_size):
        if not sock.recv_chunks:
            raise BlockingIOError()
        chunk = sock.recv_chunks.pop(0)
        if len(chunk) > buffer_size:
            sock.recv_chunks.insert(0, chunk[buffer_size:])
            chunk = chunk[:buffer_size]
        return chunk

    def socket_close(self, sock):
        sock.closed = True


class TestProtocolClients(unittest.TestCase):
    def build_os(self, socket, task):
        kernel = ScriptedKernel([socket])
        runtime = SmallOS().setKernel(kernel)
        runtime.fork([task])
        runtime.startOS()
        return runtime, kernel

    def test_redis_client_supports_ping_set_and_get(self):
        redis_socket = ScriptedSocket(
            [
                b"+PONG\r\n",
                b"+OK\r\n",
                b"$5\r\nvalue\r\n",
            ]
        )

        async def redis_job(task):
            client = SmallRedisClient(task, host="redis.local")
            await client.connect()
            pong = await client.ping()
            ok = await client.set("key", "value")
            value = await client.get("key")
            client.close()
            return (pong, ok, value)

        root = SmallTask(2, redis_job, name="redis_job")
        _, kernel = self.build_os(redis_socket, root)

        self.assertEqual(("PONG", "OK", "value"), root.result)
        self.assertTrue(redis_socket.closed)
        self.assertEqual(
            [
                b"*1\r\n$4\r\nPING\r\n",
                b"*3\r\n$3\r\nSET\r\n$3\r\nkey\r\n$5\r\nvalue\r\n",
                b"*2\r\n$3\r\nGET\r\n$3\r\nkey\r\n",
            ],
            redis_socket.sent,
        )
        self.assertIs(kernel.opened[0], redis_socket)

    def test_mqtt_client_supports_connect_subscribe_receive_and_publish(self):
        mqtt_socket = ScriptedSocket(
            [
                b"\x20\x02\x00\x00",
                b"\x90\x03\x00\x01\x00",
                b"\x30\x08\x00\x04demohi",
            ]
        )

        async def mqtt_job(task):
            client = SmallMQTTClient(task, host="broker.local", client_id="demo-client")
            await client.connect()
            suback = await client.subscribe("demo")
            message = await client.receive_message()
            await client.publish("demo", "ok")
            await client.disconnect()
            return (suback["granted_qos"], message["topic"], message["payload"])

        root = SmallTask(2, mqtt_job, name="mqtt_job")
        self.build_os(mqtt_socket, root)

        self.assertEqual((0, "demo", "hi"), root.result)
        self.assertTrue(mqtt_socket.closed)
        self.assertEqual(
            [
                b"\x10\x17\x00\x04MQTT\x04\x02\x00<\x00\x0bdemo-client",
                b"\x82\x09\x00\x01\x00\x04demo\x00",
                b"\x30\x08\x00\x04demook",
                b"\xE0\x00",
            ],
            mqtt_socket.sent,
        )

    def test_mqtt_client_supports_qos1_publish(self):
        mqtt_socket = ScriptedSocket(
            [
                b"\x20\x02\x00\x00",
                b"\x40\x02\x00\x01",
            ]
        )

        async def mqtt_job(task):
            client = SmallMQTTClient(task, host="broker.local", client_id="demo-client")
            await client.connect()
            publish_info = await client.publish("demo", "ok", qos=1)
            await client.disconnect()
            return publish_info

        root = SmallTask(2, mqtt_job, name="mqtt_qos1_publish")
        self.build_os(mqtt_socket, root)

        self.assertEqual({"qos": 1, "packet_id": 1}, root.result)
        self.assertTrue(mqtt_socket.closed)
        self.assertEqual(
            [
                b"\x10\x17\x00\x04MQTT\x04\x02\x00<\x00\x0bdemo-client",
                b"\x32\x0A\x00\x04demo\x00\x01ok",
                b"\xE0\x00",
            ],
            mqtt_socket.sent,
        )

    def test_mqtt_client_acks_inbound_qos1_messages(self):
        mqtt_socket = ScriptedSocket(
            [
                b"\x20\x02\x00\x00",
                b"\x90\x03\x00\x01\x01",
                b"\x32\x0A\x00\x04demo\x00\x07hi",
            ]
        )

        async def mqtt_job(task):
            client = SmallMQTTClient(task, host="broker.local", client_id="demo-client")
            await client.connect()
            suback = await client.subscribe("demo", qos=1)
            message = await client.receive_message()
            await client.disconnect()
            return (suback["granted_qos"], message["topic"], message["payload"], message["qos"])

        root = SmallTask(2, mqtt_job, name="mqtt_qos1_inbound")
        self.build_os(mqtt_socket, root)

        self.assertEqual((1, "demo", "hi", 1), root.result)
        self.assertTrue(mqtt_socket.closed)
        self.assertEqual(
            [
                b"\x10\x17\x00\x04MQTT\x04\x02\x00<\x00\x0bdemo-client",
                b"\x82\x09\x00\x01\x00\x04demo\x01",
                b"\x40\x02\x00\x07",
                b"\xE0\x00",
            ],
            mqtt_socket.sent,
        )

    def test_mqtt_client_supports_qos2_publish_and_receive(self):
        mqtt_socket = ScriptedSocket(
            [
                b"\x20\x02\x00\x00",
                b"\x90\x03\x00\x01\x02",
                b"\x50\x02\x00\x02",
                b"\x70\x02\x00\x02",
                b"\x34\x0A\x00\x04demo\x00\x0Bhi",
                b"\x62\x02\x00\x0B",
            ]
        )

        async def mqtt_job(task):
            client = SmallMQTTClient(task, host="broker.local", client_id="demo-client")
            await client.connect()
            suback = await client.subscribe("demo", qos=2)
            publish_info = await client.publish("demo", "ok", qos=2)
            message = await client.receive_message()
            await client.disconnect()
            return (suback["granted_qos"], publish_info["packet_id"], message["topic"], message["payload"], message["qos"])

        root = SmallTask(2, mqtt_job, name="mqtt_qos2_flow")
        self.build_os(mqtt_socket, root)

        self.assertEqual((2, 2, "demo", "hi", 2), root.result)
        self.assertTrue(mqtt_socket.closed)
        self.assertEqual(
            [
                b"\x10\x17\x00\x04MQTT\x04\x02\x00<\x00\x0bdemo-client",
                b"\x82\x09\x00\x01\x00\x04demo\x02",
                b"\x34\x0A\x00\x04demo\x00\x02ok",
                b"\x62\x02\x00\x02",
                b"\x50\x02\x00\x0B",
                b"\x70\x02\x00\x0B",
                b"\xE0\x00",
            ],
            mqtt_socket.sent,
        )


if __name__ == "__main__":
    unittest.main()
