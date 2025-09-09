#!/usr/bin/env python3
from update_waveshare._device import create_device
from IT8951 import constants

# create real device
dev = create_device(vcom=-2.06, virtual=False)
epd = dev.epd

print('width,height=', dev.width, dev.height)
print('firmware_version=', getattr(epd, 'firmware_version', None))
print('lut_version=', getattr(epd, 'lut_version', None))

try:
    print('vcom=', epd.get_vcom())
except Exception as e:
    print('get_vcom error:', e)

try:
    up0sr = epd.read_register(constants.Registers.UP0SR)
    lutafsr = epd.read_register(constants.Registers.LUTAFSR)
    print('UP0SR=', hex(up0sr))
    print('LUTAFSR=', hex(lutafsr))
except Exception as e:
    print('read_register error:', e)
