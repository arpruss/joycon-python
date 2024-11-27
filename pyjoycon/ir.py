from collections import namedtuple

_IRRegistersJoyCon = namedtuple('IRRegisters', ['resolution', 'exposure', 'maxExposure', 'leds', 'digitalGain',
                        'externalLightFilter', 'brightnessThreshold', 'leds12Intensity', 'leds34Intensity',
                        'flip', 'denoise', 'smoothingThreshold', 'interpolationThreshold', 'updateTime'])
# exposure - 0-600 microseconds                         

class IRRegistersJoyCon(_IRRegistersJoyCon):
    LED_FLASHLIGHT = 0b01
    LED_STROBE = 0b10000000
    LED_12_OFF = 0b010000 ## TODO: check
    LED_34_OFF = 0b100000 ## TODO: check
    
    def write(self, joycon):
        data = []
        if self.resolution is not None:
            data.append((0x00,0x2e,self.resolution))
            e = (31200 * self.exposure + 500) // 1000
            data.append((0x01,0x30,e & 0xFF))
            data.append((0x01,0x31,(e>>8) & 0xFF))
        if self.maxExposure is not None:
            data.append((0x01,0x32,1 if self.maxExposure else 0))
        if self.leds is not None:
            data.append((0x00,0x10,self.leds))
        if self.exposure is not None:
            data.append((0x01,0x2e,(self.digitalGain & 0xF)<<4))
            data.append((0x01,0x2f,(self.digitalGain & 0xF0)>>4))
        if self.externalLightFilter is not None:
            data.append((0x00,0x0e,1 if self.externalLightFilter else 0))
        if self.brightnessThreshold is not None:
            data.append((0x01,0x43,self.brightnessThreshhold))
        if self.leds12Intensity is not None:
            data.append((0x00,0x11,self.leds12Intensity))
        if self.leds34Intensity is not None:
            data.append((0x00,0x11,self.leds34Intensity))
        if self.flip is not None:
            data.append((0x00,0x2d,self.flip))
        if self.denoise is not None:
            data.append((0x01,0x67,1 if self.denoise else 0))
        if self.smoothingThreshold is not None:
            data.append((0x01,0x68,self.smoothingThreshold))
        if self.interpolationThreshold is not None:
            data.append((0x01,0x69,self.interpolationThreshold))
        if self.updateTime is not None:
            data.append((0x00,0x04,self.updateTime))
        elif self.resolution is not None:
            data.append((0x00,0x04,0x02d if self.resolution == 0x69 else 0x32))
        while len(data):
            if len(data)<9:
                joycon._set_mcu_registers(data+((0x00,0x07,0x01),))
                data = []
            else:
                joycon._set_mcu_registers(data[0:9])
                if len(data) == 9:
                    joycon._set_mcu_registers(((0x00,0x07,0x01),))
                data = data[9:]
                