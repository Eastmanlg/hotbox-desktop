import asyncio
import logging
import struct
from queue import Queue
from threading import Thread
import bleak

logger = logging.getLogger(__name__)

class BLEHandler:
    def __init__(self, data_queue):
        self._queue = data_queue
        self._running = False
        self._thread = None
        
        # BLE UUIDs
        self.ENV_SENSE_UUID = "0000{0:x}-0000-1000-8000-00805f9b34fb".format(0x181A)
        self.ENV_SENSE_TEMP1_UUID = "0000{0:x}-0000-1000-8000-00805f9b34fb".format(0x2A6E)
        self.ENV_SENSE_TEMP2_UUID = "0000{0:x}-0000-1000-8000-00805f9b34fb".format(0x2A1C)

    def _decode_temperature(self, data):
        temp = struct.unpack("<i", data)[0]
        
        print(temp)
        return struct.unpack("<i", data)[0] / 100

    def _callback(self, sender: bleak.BleakGATTCharacteristic, data: bytearray):
        temp = None if not data else self._decode_temperature(data)
        # Put timestamp and temperature data in queue
        timestamp = asyncio.get_event_loop().time()
        self._queue.put((timestamp, sender.uuid, temp))

    async def find_temp_sensor(self):
        return await bleak.BleakScanner.find_device_by_name('mpy-temp')

    async def run_ble(self):
        while self._running:
            try:
                device = await self.find_temp_sensor()
                if not device:
                    logger.error("Temperature sensor not found")
                    await asyncio.sleep(5)
                    continue

                async with bleak.BleakClient(device) as client:
                    service = client.services.get_service(self.ENV_SENSE_UUID)
                    if service is None:
                        logger.error("Temperature service not found")
                        continue

                    temp1_char = service.get_characteristic(self.ENV_SENSE_TEMP1_UUID)
                    temp2_char = service.get_characteristic(self.ENV_SENSE_TEMP2_UUID)

                    if None in (temp1_char, temp2_char):
                        logger.error("Temperature characteristics not found")
                        continue

                    await client.start_notify(temp1_char, self._callback)
                    await client.start_notify(temp2_char, self._callback)

                    while client.is_connected and self._running:
                        await asyncio.sleep(1)

            except Exception as e:
                logger.error(f"BLE error: {e}")
                await asyncio.sleep(5)

    def start(self):
        self._running = True
        self._thread = Thread(target=self._run_event_loop)
        self._thread.start()

    def stop(self):
        self._running = False
        if self._thread:
            self._thread.join()

    def _run_event_loop(self):
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        loop.run_until_complete(self.run_ble())
        loop.close()