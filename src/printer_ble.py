"""Paperang STX/ETX protocol over BLE, without image-processing dependencies.

Protocol references: createskyblue/paperang-miaomiaoji-tool-gen2 and
wyrtensi/paperang-cli (MIT; see vendor/PAPERANG-LICENSE).
"""
import asyncio
import struct
import zlib
from bleak import BleakClient
from bleak.backends.winrt.util import uninitialize_sta

WRITE = '49535343-8841-43f4-a8d4-ecbe34729bb3'
NOTIFY = '49535343-1e4d-4bd9-ba61-23c647249616'
REGISTER = bytes.fromhex('0218000400219576351cdf442103')


def pack(command, payload, index=0):
    return (struct.pack('<BBBH', 2, command, index, len(payload)) + payload
            + struct.pack('<I', zlib.crc32(payload) & 0xffffffff) + b'\x03')


def extract_frames(buffer):
    frames = []
    while buffer:
        if buffer[0] != 2:
            del buffer[0]
            continue
        if len(buffer) < 5:
            break
        length = struct.unpack_from('<H', buffer, 3)[0]
        if length > 4096:
            raise RuntimeError('Invalid printer response length')
        if len(buffer) < length + 10:
            break
        packet = bytes(buffer[:length + 10])
        del buffer[:length + 10]
        payload = packet[5:5 + length]
        crc = struct.unpack_from('<I', packet, 5 + length)[0]
        if packet[-1] != 3 or crc != zlib.crc32(payload) & 0xffffffff:
            raise RuntimeError('Printer response failed its integrity check')
        frames.append((packet[1], payload))
    return frames


class Connection:
    def __init__(self, address):
        self.client = BleakClient(address, timeout=20)
        self.queue = asyncio.Queue()
        self.buffer = bytearray()
        self.error = None

    def notify(self, _, data):
        self.buffer.extend(data)
        try:
            for frame in extract_frames(self.buffer):
                self.queue.put_nowait(frame)
        except Exception as exc:
            self.error = exc
            self.queue.put_nowait((-1, b''))

    async def write(self, packet):
        characteristic = self.client.services.get_characteristic(WRITE)
        if characteristic is None:
            raise RuntimeError('This printer does not expose the supported BLE service')
        size = min(180, characteristic.max_write_without_response_size)
        for offset in range(0, len(packet), size):
            await self.client.write_gatt_char(characteristic, packet[offset:offset + size], response=False)
            await asyncio.sleep(0.01)

    async def request(self, command, payload=b'\x01', expected=None, raw=None):
        while not self.queue.empty():
            self.queue.get_nowait()
        await self.write(raw if raw is not None else pack(command, payload))
        expected = command + 1 if expected is None else expected
        async with asyncio.timeout(4):
            while True:
                reply, data = await self.queue.get()
                if self.error:
                    raise self.error
                if reply == expected:
                    return data

    async def __aenter__(self):
        try:
            await self.client.connect()
            await self.client.start_notify(NOTIFY, self.notify)
            await asyncio.sleep(0.2)
            reply = await self.request(24, expected=24, raw=REGISTER)
            if reply != b'\x00':
                raise RuntimeError('Printer rejected the protocol handshake')
            return self
        except BaseException:
            await self.client.disconnect()
            raise

    async def __aexit__(self, *_):
        await self.client.disconnect()


async def _status(address, battery_only):
    async with Connection(address) as printer:
        battery = await printer.request(16)
        result = dict(address=address, connected=True, protocol='paperang-stx-ble',
                      battery_percent=battery[0] if len(battery) == 1 and battery[0] <= 100 else None,
                      battery_raw=battery.hex())
        if not battery_only:
            version = await printer.request(4)
            model = await printer.request(6)
            state = await printer.request(12)
            result.update(firmware_raw=version.hex(), model_code=model.hex(), status_raw=state.hex())
            if len(version) == 3:
                result['firmware_version'] = '.'.join(str(v) for v in reversed(version))
        return result


def status(address, battery_only=False):
    uninitialize_sta()
    return asyncio.run(_status(address, battery_only))


async def _send_raster(address, raster):
    async with Connection(address) as printer:
        # Require a live response before issuing any paper-consuming command.
        await printer.request(16)
        # Match the P2 serial reference's density and paper-type setup.
        for command, value in ((25, 75), (44, 0)):
            await printer.write(pack(command, bytes([value])))
            await asyncio.sleep(.2)
        # 1008 = 14 complete rows of a 576-dot print head.
        for index, offset in enumerate(range(0, len(raster), 1008)):
            await printer.write(pack(0, raster[offset:offset + 1008], index & 255))
        await asyncio.sleep(.5)
        await printer.request(16)
    return dict(sent=True, bytes_sent=len(raster),
                message='Raster sent; check the physical paper to confirm the result.')


def send_raster(address, raster, *, allow_paper_use=False):
    if not allow_paper_use:
        raise ValueError('Printing requires explicit paper-use approval')
    if not address or not raster or len(raster) % 72 or len(raster) > 72 * 12072:
        raise ValueError('Invalid address or raster dimensions')
    uninitialize_sta()
    return asyncio.run(_send_raster(address, raster))
