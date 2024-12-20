from .constants import JOYCON_VENDOR_ID, JOYCON_PRODUCT_IDS
from .constants import JOYCON_L_PRODUCT_ID, JOYCON_R_PRODUCT_ID
from .ir import IRRegisters
import hid
import time
import threading
import struct
from typing import Optional
from collections import namedtuple

# TODO: disconnect, power off sequence

class JoyCon:
    _INPUT_REPORT_SIZE = 360
    _INPUT_REPORT_PERIOD = 0.015
    IR_POINTING   = 4
    IR_CLUSTERING = 6
    IR_IMAGE      = 7
    
    _IR_FRAGMENT_SIZE = 300
    
    _RUMBLE_DATA = b'\x00\x01\x40\x40\x00\x01\x40\x40'
    #_RUMBLE_DATA = b'\x00\x00\x00\x00\x00\x00\x00\x00'

    vendor_id  : int
    product_id : int
    serial     : Optional[str]
    simple_mode: bool
    color_body : (int, int, int)
    color_btn  : (int, int, int)

    def __init__(self, vendor_id: int, product_id: int, serial: str = None, simple_mode=False, ir_mode=None, ir_registers=None):
        if vendor_id != JOYCON_VENDOR_ID:
            raise ValueError(f'vendor_id is invalid: {vendor_id!r}')

        if product_id not in JOYCON_PRODUCT_IDS:
            raise ValueError(f'product_id is invalid: {product_id!r}')

        self.ir_mode     = ir_mode
        self.ir_registers = ir_registers
        self.vendor_id   = vendor_id
        self.product_id  = product_id
        self.serial      = serial
        self.simple_mode = simple_mode  # TODO: It's for reporting mode 0x3f

        # setup internal state
        self._input_hooks = []
        self._input_report = bytes(self._INPUT_REPORT_SIZE)
        self._packet_number = 0
        self.set_accel_calibration((0, 0, 0), (1, 1, 1))
        self.set_gyro_calibration((0, 0, 0), (1, 1, 1))

        # connect to joycon
        self._joycon_device = self._open(vendor_id, product_id, serial=None)
        self._read_joycon_data()
        
        if self.ir_mode is not None:
            if self.ir_registers is None:
                self.ir_registers = IRRegisters()
                self.ir_registers.defaults(self.ir_mode)
        
        self._setup_sensors()

        # start talking with the joycon in a daemon thread
        self._update_input_report_thread \
            = threading.Thread(target=self._update_input_report)
        self._update_input_report_thread.setDaemon(True)
        self._update_input_report_thread.start()
        
    def _show(self, data, direction):
        print(direction + (' '.join(('%02x'%datum for datum in data))))
       
    def _request_ir_report(self,fragmentAcknowledge=0,ignore=False):
        self._write_output_report(b'\x11', b'\x03', b'\x00\x00\x00'+bytes((fragmentAcknowledge,))+(b'\x00'*33)+b'\xFF', crcLocation=47, crcStart=11, crcLength=36, confirm=((0,0x31),) if ignore else None)            
        
    def _disable_ir_mode(self):
        self._write_output_report(b'\x01', b'\x21', b'\x23\x01\x02', crcLocation=48, crcStart=12, crcLength=36)
        
    def _set_report_type(self, reportType):
        self._report_type = reportType
        self._write_output_report(b'\x01', b'\x03', bytes((reportType,)), confirm=((0xD,0x80),(0xE,0x3)))
        
    def _enable_ir_mode(self, retries=16):
        self._set_report_type(0x31)
        if self.ir_registers is None or self.ir_registers.resolution is None or self.ir_registers.resolution <= 0:
            # TODO: handle more complex binning/skipping
            self.ir_resolution = 320
        else:
            self.ir_resolution = self.ir_registers.resolution
        self._ir_fragments = 1
        if self.ir_mode == JoyCon.IR_IMAGE:
            if self.ir_resolution == 320:
                self._ir_fragments = 0xFF
            elif self.ir_resolution == 160:
                self._ir_fragments = 0x3f
            elif self.ir_resolution == 80:
                self._ir_fragments = 0x0f
            elif self.ir_resolution == 40:
                self._ir_fragments = 0x03
        
        # init mcu
        self._write_output_report(b'\x01', b'\x22', b'\x01', confirm=((0xD,0x80),(0xE,0x22)))
        # get status
        self._write_output_report(b'\x11', b'\x01', b'', confirm=((0,self._report_type),(49,0x01),(56,0x01)))
        # set mcu mode
        self._write_output_report(b'\x01', b'\x21', b'\x01\x00\x05', crcLocation=48, crcStart=12, crcLength=36, confirm=((0,0x21), (15,0x01), (22, 0x01)))
        # get status
        self._write_output_report(b'\x11', b'\x01', b'', confirm=((0,self._report_type),(49,0x01),(56,0x05)))
        # set ir mode
        args = struct.pack('<BBBBHH', 0x23, 0x01, self.ir_mode, self._ir_fragments, 0x0500, 0x1800)
        self._write_output_report(b'\x01', b'\x21', args, crcLocation=48, crcStart=12, crcLength=36, confirm=((0,0x21),(15,0x0b)))

        if self.ir_registers is not None:
            self.ir_registers.write(self)
            
        for retries in range(500):
            self._request_ir_report()
            report = self._read_input_report()
            if self._have_ir_data(report):
                break
        else:
            raise IOError("No IR data received")

        if self.ir_registers is not None:
            self.ir_registers.write(self)

        if self.ir_mode == JoyCon.IR_IMAGE:
            if self.ir_registers is not None:
                self.ir_registers.write(self)
            self._ir_fragment = 0
            self._ir_data = [0,] * (self._ir_fragments * JoyCon._IR_FRAGMENT_SIZE)
            self._ir_last_image = None
            self._ir_last_fragment = 0
            
        self._request_ir_report(fragmentAcknowledge=0)
        return True
        
    def _get_mcu_registers(self,page):
        cmd = bytes((0x03,0x01,page,0x00,0x7f))
        report = self._write_output_report(b'\x11',b'\x03',cmd,crcLocation=47,crcStart=11,crcLength=36,
                    confirm=((49,0x1b),(51,page),(52,0x00)))
        if not report:
            raise IOError("Cannot read MCU registers")
        else:
            return tuple(report[54+i] for i in range(report[52]+report[53]))

    def _set_mcu_registers(self, registers):
        count = len(registers)
        if count > 9:
            raise ValueError("Too many registers")
        cmd = bytes((0x23,0x04,count,))
        for page,reg,value in registers:
            cmd += bytes((page,reg,value))
        if count < 9:
            cmd += bytes((0,0,0)) * (9-count)
        self._write_output_report(b'\x01', b'\x21', cmd, crcLocation=48, crcStart=12, crcLength=36, confirm=((0,0x21),(14,0x21)))
        #time.sleep(0.015)
        return True

    def _open(self, vendor_id, product_id, serial):
        try:
            if hasattr(hid, "device"):  # hidapi
                _joycon_device = hid.device()
                _joycon_device.open(vendor_id, product_id, serial)
            elif hasattr(hid, "Device"):  # hid
                _joycon_device = hid.Device(vendor_id, product_id, serial)
            else:
                raise Exception("Implementation of hid is not recognized!")
        except IOError as e:
            raise IOError('joycon connect failed') from e
        return _joycon_device

    def _close(self):
        if hasattr(self, "_joycon_device"):
            self._joycon_device.close()
            del self._joycon_device

    def _read_input_report(self) -> bytes:
        out = bytes(self._joycon_device.read(self._INPUT_REPORT_SIZE))
        return out
        
    crc8_table = [
        0x00, 0x07, 0x0E, 0x09, 0x1C, 0x1B, 0x12, 0x15, 0x38, 0x3F, 0x36, 0x31, 0x24, 0x23, 0x2A, 0x2D,
        0x70, 0x77, 0x7E, 0x79, 0x6C, 0x6B, 0x62, 0x65, 0x48, 0x4F, 0x46, 0x41, 0x54, 0x53, 0x5A, 0x5D,
        0xE0, 0xE7, 0xEE, 0xE9, 0xFC, 0xFB, 0xF2, 0xF5, 0xD8, 0xDF, 0xD6, 0xD1, 0xC4, 0xC3, 0xCA, 0xCD,
        0x90, 0x97, 0x9E, 0x99, 0x8C, 0x8B, 0x82, 0x85, 0xA8, 0xAF, 0xA6, 0xA1, 0xB4, 0xB3, 0xBA, 0xBD,
        0xC7, 0xC0, 0xC9, 0xCE, 0xDB, 0xDC, 0xD5, 0xD2, 0xFF, 0xF8, 0xF1, 0xF6, 0xE3, 0xE4, 0xED, 0xEA,
        0xB7, 0xB0, 0xB9, 0xBE, 0xAB, 0xAC, 0xA5, 0xA2, 0x8F, 0x88, 0x81, 0x86, 0x93, 0x94, 0x9D, 0x9A,
        0x27, 0x20, 0x29, 0x2E, 0x3B, 0x3C, 0x35, 0x32, 0x1F, 0x18, 0x11, 0x16, 0x03, 0x04, 0x0D, 0x0A,
        0x57, 0x50, 0x59, 0x5E, 0x4B, 0x4C, 0x45, 0x42, 0x6F, 0x68, 0x61, 0x66, 0x73, 0x74, 0x7D, 0x7A,
        0x89, 0x8E, 0x87, 0x80, 0x95, 0x92, 0x9B, 0x9C, 0xB1, 0xB6, 0xBF, 0xB8, 0xAD, 0xAA, 0xA3, 0xA4,
        0xF9, 0xFE, 0xF7, 0xF0, 0xE5, 0xE2, 0xEB, 0xEC, 0xC1, 0xC6, 0xCF, 0xC8, 0xDD, 0xDA, 0xD3, 0xD4,
        0x69, 0x6E, 0x67, 0x60, 0x75, 0x72, 0x7B, 0x7C, 0x51, 0x56, 0x5F, 0x58, 0x4D, 0x4A, 0x43, 0x44,
        0x19, 0x1E, 0x17, 0x10, 0x05, 0x02, 0x0B, 0x0C, 0x21, 0x26, 0x2F, 0x28, 0x3D, 0x3A, 0x33, 0x34,
        0x4E, 0x49, 0x40, 0x47, 0x52, 0x55, 0x5C, 0x5B, 0x76, 0x71, 0x78, 0x7F, 0x6A, 0x6D, 0x64, 0x63,
        0x3E, 0x39, 0x30, 0x37, 0x22, 0x25, 0x2C, 0x2B, 0x06, 0x01, 0x08, 0x0F, 0x1A, 0x1D, 0x14, 0x13,
        0xAE, 0xA9, 0xA0, 0xA7, 0xB2, 0xB5, 0xBC, 0xBB, 0x96, 0x91, 0x98, 0x9F, 0x8A, 0x8D, 0x84, 0x83,
        0xDE, 0xD9, 0xD0, 0xD7, 0xC2, 0xC5, 0xCC, 0xCB, 0xE6, 0xE1, 0xE8, 0xEF, 0xFA, 0xFD, 0xF4, 0xF3
    ]
        
    def _crc8(self, data, start, length):
        crc8 = 0
        for i in range(length):
            crc8 = JoyCon.crc8_table[crc8^(0xFF & data[start+i])]
        return crc8

    def _write_output_report(self, command, subcommand, argument, crcLocation=None, crcStart=None, crcLength=None, confirm=None, confirmRetries=16):
        r = confirmRetries
        while r > 0:
            # TODO: add documentation
            data = b''.join([
                command,
                self._packet_number.to_bytes(1, byteorder='little'),
                self._RUMBLE_DATA,
                subcommand,
                argument,
            ])
            if crcLocation is not None:
                if len(data) < crcLocation:
                    data += bytes((0,)) * (crcLocation - len(data))
                data = data[:crcLocation] + self._crc8(data, crcStart, crcLength).to_bytes(1) + data[crcLocation+1:]
                
            if len(data)>49:
                data = data[:49]
            elif len(data)<49:
                data += bytes((0,))*(49-len(data))
            
            self._joycon_device.write(data)
            self._packet_number = (self._packet_number + 1) & 0xF
            
            if confirm is None:
                return True
                
            r2 = confirmRetries
            while r2 > 0:
                report = self._read_input_report()
                haveRightReportType = None
                for pos,value in confirm:
                    if pos == 0 and len(report) >= 1 and report[0] == value:
                        haveRightReportType = True
                    elif len(report)<=pos or report[pos] != value:
                        break
                else:
                    return report
                    
                if haveRightReportType:
                    r2 = 0
                else:
                    r2 -= 1
                
            r -= 1
        raise IOError("Cannot confirm subcommand %02x" % subcommand[0])

    def _send_subcmd_get_response(self, subcommand, argument) -> (bool, bytes):
        # TODO: handle subcmd when daemon is running
        self._write_output_report(b'\x01', subcommand, argument)

        report = self._read_input_report()
        while report[0] != 0x21:  # TODO, avoid this, await daemon instead
            report = self._read_input_report()

        # TODO, remove, see the todo above
        assert report[1:2] != subcommand, "THREAD carefully"

        # TODO: determine if the cut bytes are worth anything

        return report[13] & 0x80, report[13:]  # (ack, data)

    def _spi_flash_read(self, address, size) -> bytes:
        assert size <= 0x1d
        argument = address.to_bytes(4, "little") + size.to_bytes(1, "little")
        ack, report = self._send_subcmd_get_response(b'\x10', argument)
        if not ack:
            raise IOError("After SPI read @ {address:#06x}: got NACK")

        if report[:2] != b'\x90\x10':
            raise IOError("Something else than the expected ACK was recieved!")
        assert report[2:7] == argument, (report[2:5], argument)

        return report[7:size+7]

    def _update_input_report(self):  # daemon thread
        while True:
            report = self._read_input_report()
            # TODO, handle input reports of type 0x21 and 0x3f
            while report[0] != 0x30 and report[0] != 0x31:
                report = self._read_input_report()
                
            self._input_report = report
            if report[0] == 0x31 and self.ir_mode is not None:
                if self._ir_fragments > 1:
                    if report[49] == 0x03:
                        f = report[52]
                        #print(f,self._ir_fragment,self._ir_fragments)
                        offset = f * JoyCon._IR_FRAGMENT_SIZE
                        self._ir_data[offset:offset+JoyCon._IR_FRAGMENT_SIZE] = report[59:59+300]
                        if f == self._ir_fragments:
                            if f == self._ir_last_fragment:
                                self._request_ir_report(0)
                                self._ir_last_image = None
                            else:
                                self._request_ir_report(f)
                                self._ir_last_image = self._ir_data
                                self._ir_data = [0,]*(self._ir_fragments * JoyCon._IR_FRAGMENT_SIZE)
                        else:
                            self._request_ir_report(f)
                            self._ir_last_image = None
                        self._ir_last_fragment = f
                        """
                        if f == (self._ir_fragment + 1) % (self._ir_fragments + 1):
                            self._ir_fragment = f
                            self._request_ir_report(f) #f if f <= self._ir_fragments else 0)
                            self._ir_data += report[59:59+300]
                            if f == self._ir_fragments:
                                l = len(self._ir_data)
                                n = self.ir_resolution * self.ir_resolution * 3 // 4
                                if n < l:
                                    self._ir_last_image = self._ir_data[:n]
                                elif n == l:
                                    self._ir_last_image = self._ir_data
                                else:
                                    self._ir_last_image = self._ir_data + [0,]*(n - l)
                                self._ir_data = []
                            else:
                                self._ir_last_image = None"""
                    else:
                        self._request_ir_report(self._ir_fragment) # TODO: handle missing
                else:
                    self._request_ir_report()
                
            for callback in self._input_hooks:
                callback(self)

    def _read_joycon_data(self):
        color_data = self._spi_flash_read(0x6050, 6)

        # TODO: use this
        # stick_cal_addr = 0x8012 if self.is_left else 0x801D
        # stick_cal  = self._spi_flash_read(stick_cal_addr, 8)

        # user IME data
        if self._spi_flash_read(0x8026, 2) == b"\xB2\xA1":
            # print(f"Calibrate {self.serial} IME with user data")
            imu_cal = self._spi_flash_read(0x8028, 24)

        # factory IME data
        else:
            # print(f"Calibrate {self.serial} IME with factory data")
            imu_cal = self._spi_flash_read(0x6020, 24)

        self.color_body = tuple(color_data[:3])
        self.color_btn  = tuple(color_data[3:])

        self.set_accel_calibration((
                self._to_int16le_from_2bytes(imu_cal[ 0], imu_cal[ 1]),
                self._to_int16le_from_2bytes(imu_cal[ 2], imu_cal[ 3]),
                self._to_int16le_from_2bytes(imu_cal[ 4], imu_cal[ 5]),
            ), (
                self._to_int16le_from_2bytes(imu_cal[ 6], imu_cal[ 7]),
                self._to_int16le_from_2bytes(imu_cal[ 8], imu_cal[ 9]),
                self._to_int16le_from_2bytes(imu_cal[10], imu_cal[11]),
            )
        )
        self.set_gyro_calibration((
                self._to_int16le_from_2bytes(imu_cal[12], imu_cal[13]),
                self._to_int16le_from_2bytes(imu_cal[14], imu_cal[15]),
                self._to_int16le_from_2bytes(imu_cal[16], imu_cal[17]),
            ), (
                self._to_int16le_from_2bytes(imu_cal[18], imu_cal[19]),
                self._to_int16le_from_2bytes(imu_cal[20], imu_cal[21]),
                self._to_int16le_from_2bytes(imu_cal[22], imu_cal[23]),
            )
        )

    def _setup_sensors(self):
        # Enable 6 axis sensors
        self._write_output_report(b'\x01', b'\x40', b'\x01')
        # It needs delta time to update the setting
        time.sleep(0.02)

        if self.ir_mode is None:
            # Change format of input report
            self._disable_ir_mode()
            self._set_report_type(0x30)
        else: 
            self._enable_ir_mode()
            
        time.sleep(0.02)

    @staticmethod
    def _to_int16le_from_2bytes(hbytebe, lbytebe):
        uint16le = (lbytebe << 8) | hbytebe
        int16le = uint16le if uint16le < 32768 else uint16le - 65536
        return int16le

    def _get_nbit_from_input_report(self, offset_byte, offset_bit, nbit):
        byte = self._input_report[offset_byte]
        return (byte >> offset_bit) & ((1 << nbit) - 1)

    def __del__(self):
        self._close()

    def set_gyro_calibration(self, offset_xyz=None, coeff_xyz=None):
        if offset_xyz:
            self._GYRO_OFFSET_X, \
            self._GYRO_OFFSET_Y, \
            self._GYRO_OFFSET_Z = offset_xyz
        if coeff_xyz:
            cx, cy, cz = coeff_xyz
            self._GYRO_COEFF_X = 0x343b / cx if cx != 0x343b else 1
            self._GYRO_COEFF_Y = 0x343b / cy if cy != 0x343b else 1
            self._GYRO_COEFF_Z = 0x343b / cz if cz != 0x343b else 1

    def set_accel_calibration(self, offset_xyz=None, coeff_xyz=None):
        if offset_xyz:
            self._ACCEL_OFFSET_X, \
            self._ACCEL_OFFSET_Y, \
            self._ACCEL_OFFSET_Z = offset_xyz
        if coeff_xyz:
            cx, cy, cz = coeff_xyz
            self._ACCEL_COEFF_X = 0x4000 / cx if cx != 0x4000 else 1
            self._ACCEL_COEFF_Y = 0x4000 / cy if cy != 0x4000 else 1
            self._ACCEL_COEFF_Z = 0x4000 / cz if cz != 0x4000 else 1

    def register_update_hook(self, callback):
        self._input_hooks.append(callback)
        return callback  # this makes it so you could use it as a decorator

    def is_left(self):
        return self.product_id == JOYCON_L_PRODUCT_ID

    def is_right(self):
        return self.product_id == JOYCON_R_PRODUCT_ID

    def get_battery_charging(self):
        return self._get_nbit_from_input_report(2, 4, 1)

    def get_battery_level(self):
        return self._get_nbit_from_input_report(2, 5, 3)

    def get_button_y(self):
        return self._get_nbit_from_input_report(3, 0, 1)

    def get_button_x(self):
        return self._get_nbit_from_input_report(3, 1, 1)

    def get_button_b(self):
        return self._get_nbit_from_input_report(3, 2, 1)

    def get_button_a(self):
        return self._get_nbit_from_input_report(3, 3, 1)

    def get_button_right_sr(self):
        return self._get_nbit_from_input_report(3, 4, 1)

    def get_button_right_sl(self):
        return self._get_nbit_from_input_report(3, 5, 1)

    def get_button_r(self):
        return self._get_nbit_from_input_report(3, 6, 1)

    def get_button_zr(self):
        return self._get_nbit_from_input_report(3, 7, 1)

    def get_button_minus(self):
        return self._get_nbit_from_input_report(4, 0, 1)

    def get_button_plus(self):
        return self._get_nbit_from_input_report(4, 1, 1)

    def get_button_r_stick(self):
        return self._get_nbit_from_input_report(4, 2, 1)

    def get_button_l_stick(self):
        return self._get_nbit_from_input_report(4, 3, 1)

    def get_button_home(self):
        return self._get_nbit_from_input_report(4, 4, 1)

    def get_button_capture(self):
        return self._get_nbit_from_input_report(4, 5, 1)

    def get_button_charging_grip(self):
        return self._get_nbit_from_input_report(4, 7, 1)

    def get_button_down(self):
        return self._get_nbit_from_input_report(5, 0, 1)

    def get_button_up(self):
        return self._get_nbit_from_input_report(5, 1, 1)

    def get_button_right(self):
        return self._get_nbit_from_input_report(5, 2, 1)

    def get_button_left(self):
        return self._get_nbit_from_input_report(5, 3, 1)

    def get_button_left_sr(self):
        return self._get_nbit_from_input_report(5, 4, 1)

    def get_button_left_sl(self):
        return self._get_nbit_from_input_report(5, 5, 1)

    def get_button_l(self):
        return self._get_nbit_from_input_report(5, 6, 1)

    def get_button_zl(self):
        return self._get_nbit_from_input_report(5, 7, 1)

    def get_stick_left_horizontal(self):
        return self._get_nbit_from_input_report(6, 0, 8) \
            | (self._get_nbit_from_input_report(7, 0, 4) << 8)

    def get_stick_left_vertical(self):
        return self._get_nbit_from_input_report(7, 4, 4) \
            | (self._get_nbit_from_input_report(8, 0, 8) << 4)

    def get_stick_right_horizontal(self):
        return self._get_nbit_from_input_report(9, 0, 8) \
            | (self._get_nbit_from_input_report(10, 0, 4) << 8)

    def get_stick_right_vertical(self):
        return self._get_nbit_from_input_report(10, 4, 4) \
            | (self._get_nbit_from_input_report(11, 0, 8) << 4)

    def get_accel_x(self, sample_idx=0):
        if sample_idx not in (0, 1, 2):
            raise IndexError('sample_idx should be between 0 and 2')
        data = self._to_int16le_from_2bytes(
            self._input_report[13 + sample_idx * 12],
            self._input_report[14 + sample_idx * 12])
        return (data - self._ACCEL_OFFSET_X) * self._ACCEL_COEFF_X

    def get_accel_y(self, sample_idx=0):
        if sample_idx not in (0, 1, 2):
            raise IndexError('sample_idx should be between 0 and 2')
        data = self._to_int16le_from_2bytes(
            self._input_report[15 + sample_idx * 12],
            self._input_report[16 + sample_idx * 12])
        return (data - self._ACCEL_OFFSET_Y) * self._ACCEL_COEFF_Y

    def get_accel_z(self, sample_idx=0):
        if sample_idx not in (0, 1, 2):
            raise IndexError('sample_idx should be between 0 and 2')
        data = self._to_int16le_from_2bytes(
            self._input_report[17 + sample_idx * 12],
            self._input_report[18 + sample_idx * 12])
        return (data - self._ACCEL_OFFSET_Z) * self._ACCEL_COEFF_Z

    def get_gyro_x(self, sample_idx=0):
        if sample_idx not in (0, 1, 2):
            raise IndexError('sample_idx should be between 0 and 2')
        data = self._to_int16le_from_2bytes(
            self._input_report[19 + sample_idx * 12],
            self._input_report[20 + sample_idx * 12])
        return (data - self._GYRO_OFFSET_X) * self._GYRO_COEFF_X

    def get_gyro_y(self, sample_idx=0):
        if sample_idx not in (0, 1, 2):
            raise IndexError('sample_idx should be between 0 and 2')
        data = self._to_int16le_from_2bytes(
            self._input_report[21 + sample_idx * 12],
            self._input_report[22 + sample_idx * 12])
        return (data - self._GYRO_OFFSET_Y) * self._GYRO_COEFF_Y

    def get_gyro_z(self, sample_idx=0):
        if sample_idx not in (0, 1, 2):
            raise IndexError('sample_idx should be between 0 and 2')
        data = self._to_int16le_from_2bytes(
            self._input_report[23 + sample_idx * 12],
            self._input_report[24 + sample_idx * 12])
        return (data - self._GYRO_OFFSET_Z) * self._GYRO_COEFF_Z
        
    def get_ir_cluster(self, data):
        brightness,pixels,cm_y_64,cm_x_64,y_start,y_end,x_start,x_end = struct.unpack("<HHHHHHHH", data)
        return namedtuple("ir_cluster", ["brightness", "pixels", "cm", "start", "end"])(
            brightness, pixels, (cm_x_64/64.,cm_y_64/64.), (x_start,y_start), (x_end,y_end));
        
    def _have_ir_data(self, report):
        return self.ir_mode is not None and report[0] == 0x31 and report[49] == 0x03 and report[51] == self.ir_mode
        
    def get_ir_image(self):
        return self._ir_last_image

    def get_ir_clusters(self):
        if self.ir_mode == JoyCon.IR_POINTING or self.ir_mode == JoyCon.IR_CLUSTERING:
            clusters = []
            if self._have_ir_data(self._input_report):
                i = 61
                while i + 16 <= 59+300:
                    if self.ir_mode == JoyCon.IR_POINTING and (i == 61 + 48 or i == 61 + 97 or i == 61 + 146 or i == 61 + 195 or i == 61 + 244):
                        i += 1
                    if self._input_report[i] != 0 or self._input_report[i+1] !=0:
                        clusters.append(self.get_ir_cluster(self._input_report[i:i+16]))
                    i += 16
            return clusters
        else:
            return None

    def get_status(self) -> dict:
        out = {
            "battery": {
                "charging": self.get_battery_charging(),
                "level": self.get_battery_level(),
            },
            "buttons": {
                "right": {
                    "y": self.get_button_y(),
                    "x": self.get_button_x(),
                    "b": self.get_button_b(),
                    "a": self.get_button_a(),
                    "sr": self.get_button_right_sr(),
                    "sl": self.get_button_right_sl(),
                    "r": self.get_button_r(),
                    "zr": self.get_button_zr(),
                },
                "shared": {
                    "minus": self.get_button_minus(),
                    "plus": self.get_button_plus(),
                    "r-stick": self.get_button_r_stick(),
                    "l-stick": self.get_button_l_stick(),
                    "home": self.get_button_home(),
                    "capture": self.get_button_capture(),
                    "charging-grip": self.get_button_charging_grip(),
                },
                "left": {
                    "down": self.get_button_down(),
                    "up": self.get_button_up(),
                    "right": self.get_button_right(),
                    "left": self.get_button_left(),
                    "sr": self.get_button_left_sr(),
                    "sl": self.get_button_left_sl(),
                    "l": self.get_button_l(),
                    "zl": self.get_button_zl(),
                }
            },
            "analog-sticks": {
                "left": {
                    "horizontal": self.get_stick_left_horizontal(),
                    "vertical": self.get_stick_left_vertical(),
                },
                "right": {
                    "horizontal": self.get_stick_right_horizontal(),
                    "vertical": self.get_stick_right_vertical(),
                },
            },
            "accel": {
                "x": self.get_accel_x(),
                "y": self.get_accel_y(),
                "z": self.get_accel_z(),
            },
            "gyro": {
                "x": self.get_gyro_x(),
                "y": self.get_gyro_y(),
                "z": self.get_gyro_z(),
            }
        }
        if self.ir_mode is not None:
            if self.ir_mode == JoyCon.IR_CLUSTERING or self.ir_mode == JoyCon.IR_POINTING:
                out["ir_clusters"] = self.get_ir_clusters()
            if self._ir_last_image:
                out["ir_image"] = self._ir_last_image
        return out

    def set_player_lamp_on(self, on_pattern: int):
        self._write_output_report(
            b'\x01', b'\x30',
            (on_pattern & 0xF).to_bytes(1, byteorder='little'))

    def set_player_lamp_flashing(self, flashing_pattern: int):
        self._write_output_report(
            b'\x01', b'\x30',
            ((flashing_pattern & 0xF) << 4).to_bytes(1, byteorder='little'))

    def set_player_lamp(self, pattern: int):
        self._write_output_report(
            b'\x01', b'\x30',
            pattern.to_bytes(1, byteorder='little'))

    def disconnect_device(self):
        self._write_output_report(b'\x01', b'\x06', b'\x00')


if __name__ == '__main__':
    import pyjoycon.device as d
    ids = d.get_L_id() if None not in d.get_L_id() else d.get_R_id()

    if None not in ids:
        joycon = JoyCon(*ids)
        lamp_pattern = 0
        while True:
            print(joycon.get_status())
            joycon.set_player_lamp_on(lamp_pattern)
            lamp_pattern = (lamp_pattern + 1) & 0xf
            time.sleep(0.2)
