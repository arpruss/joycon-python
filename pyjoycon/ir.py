from . import joycon

# exposure - 0-600 microseconds                         
# pointingThreshold 0-7

class IRRegisters:
    LED_FLASHLIGHT = 0b01
    LED_STROBE = 0b10000000
    LED_12_OFF = 0b010000 ## TODO: check
    LED_34_OFF = 0b100000 ## TODO: check
    fields = ('resolution', 'exposure', 'maxExposure', 'leds', 'digitalGain',
                        'externalLightFilter', 'brightnessThreshold', 'leds12Intensity', 'leds34Intensity',
                        'flip', 'denoise', 'smoothingThreshold', 'interpolationThreshold', 'updateTime',
                        'pointingThreshold')
    
    def __init__(self, **kwargs):
        for arg in IRRegisters.fields:
            if arg in kwargs:
                setattr(self,arg,kwargs[arg])
            else:
                setattr(self,arg,None)
                
    def __repr__(self):
        return ", ".join(f+"="+repr(getattr(self,f)) for f in IRRegisters.fields)
        
    def defaults(self, mode):
        if mode == joycon.JoyCon.IR_CLUSTERING:
            self.resolution=320
            self.exposure=200
            self.maxExposure=0
            self.leds=16
            self.digitalGain=1
            self.externalLightFilter=1
            self.brightnessThreshold=200
            self.leds12Intensity=13
            self.leds34Intensity=13
            self.flip=2
            self.denoise=1
            self.smoothingThreshold=35
            self.interpolationThreshold=68
            self.updateTime=50
            self.pointingThreshold=0
        elif mode == joycon.JoyCon.IR_IMAGE:
            self.resolution=320
            self.exposure=200
            self.maxExposure=0
            self.leds=0
            self.digitalGain=16
            self.externalLightFilter=0
            self.brightnessThreshold=200
            self.leds12Intensity=13
            self.leds34Intensity=13
            self.flip=2
            self.denoise=0
            self.smoothingThreshold=35
            self.interpolationThreshold=68
            self.updateTime=50
            self.pointingThreshold=1
        elif mode == joycon.JoyCon.IR_IMAGE:
            pass # TODO
    
    def read(self, j):
        page0 = j._get_mcu_registers(0x00)
        page1 = j._get_mcu_registers(0x01)
        r = page0[0x2e]
        if r == 0b00000000:
            self.resolution = 320
        elif r == 0b01010000:
            self.resolution = 160
        elif r == 0b01100100:
            self.resolution = 80
        elif r == 0b01101001:
            self.resolution = 40
        else:
            self.resolution = -(r & 0xFF)
        e = (page1[0x30] & 0xFF) | ((page1[0x31] & 0xFF)<<8)
        self.exposure = (e * 1000 + 31200//2) // 31200
        self.maxExposure = page1[0x32]
        self.leds = page0[0x10]
        self.digitalGain = ((page1[0x2e] & 0xFF) | ((page1[0x2f] & 0xFF)<<8)) >> 4
        self.externalLightFilter = 1 if page0[0x0e] else 3
        self.brightnessThreshold = page1[0x43]
        self.leds12Intensity = page0[0x11]
        self.leds34Intensity = page0[0x12]
        self.flip = page0[0x2d]
        self.denoise = page1[0x67]
        self.smoothingThreshold = page1[0x68]
        self.interpolationThreshold = page1[0x69]
        self.updateTime = page0[0x04]
        self.pointingThreshold = page1[0x21]
    
    def write(self, j):
        data = []
        if self.resolution is not None:
            if self.resolution == 320:
                r = 0b00000000
            elif self.resolution == 160:
                r = 0b01010000
            elif self.resolution == 80:
                r = 0b01100100
            elif self.resolution == 40:
                r = 0b01101001
            else:
                r = -self.resolution
            data.append((0x00,0x2e,r))
        if self.exposure is not None:
            e = (31200 * self.exposure + 500) // 1000
            data.append((0x01,0x30,e & 0xFF))
            data.append((0x01,0x31,(e>>8) & 0xFF))
        if self.maxExposure is not None:
            data.append((0x01,0x32,1 if self.maxExposure else 0))
        if self.leds is not None:
            data.append((0x00,0x10,self.leds))
        if self.digitalGain is not None:
            data.append((0x01,0x2e,(self.digitalGain & 0xF)<<4))
            data.append((0x01,0x2f,(self.digitalGain & 0xF0)>>4))
        if self.externalLightFilter is not None:
            data.append((0x00,0x0e,3 if self.externalLightFilter else 0))
        if self.brightnessThreshold is not None:
            data.append((0x01,0x43,self.brightnessThreshold))
        if self.leds12Intensity is not None:
            data.append((0x00,0x11,self.leds12Intensity))
        if self.leds34Intensity is not None:
            data.append((0x00,0x12,self.leds34Intensity))
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
            data.append((0x00,0x04,0x02d if self.resolution == 40 else 0x32))
        if self.pointingThreshold is not None:
            data.append((0x01,0x21,self.pointingThreshold))
        while len(data):
            if len(data)<9:
                j._set_mcu_registers(data+[(0x00,0x07,0x01),])
                data = []
            else:
                j._set_mcu_registers(data[0:9])
                if len(data) == 9:
                    j._set_mcu_registers([(0x00,0x07,0x01),])
                data = data[9:]
                