import time
from machine import I2C

# ----------------------------
# User settings (your hardware)
# ----------------------------
INA228_ADDRESS = 0x40

RSHUNT_OHMS = 0.003          # 3 mΩ shunt
MAX_EXPECTED_CURRENT_A = 25  # Max 25 A

# Must be 0 for 25A*3mΩ = 75mV (needs ±163.84mV range)
ADCRANGE = 0  # CONFIG.ADCRANGE: 0=±163.84mV, 1=±40.96mV


class INA228:
    # ----------------------------
    # Register map (datasheet Table 7-3)
    # ----------------------------
    REG_CONFIG          = 0x00
    REG_ADC_CONFIG      = 0x01
    REG_SHUNT_CAL       = 0x02
    REG_SHUNT_TEMPCO    = 0x03
    REG_VSHUNT          = 0x04
    REG_VBUS            = 0x05
    REG_DIETEMP         = 0x06
    REG_CURRENT         = 0x07
    REG_POWER           = 0x08
    REG_ENERGY          = 0x09  # 40-bit
    REG_CHARGE          = 0x0A  # 40-bit
    REG_DIAG_ALRT       = 0x0B
    REG_SOVL            = 0x0C
    REG_SUVL            = 0x0D
    REG_BOVL            = 0x0E
    REG_BUVL            = 0x0F
    REG_TEMP_LIMIT      = 0x10
    REG_PWR_LIMIT       = 0x11
    REG_MANUFACTURER_ID = 0x3E
    REG_DEVICE_ID       = 0x3F

    # ----------------------------
    # CONFIG bitfields (datasheet Table 7-5)
    # ----------------------------
    CONFIG_RST_BIT       = 15
    CONFIG_RSTACC_BIT    = 14
    CONFIG_CONVDLY_SHIFT = 6
    CONFIG_TEMPCOMP_BIT  = 5
    CONFIG_ADCRANGE_BIT  = 4

    # ----------------------------
    # ADC_CONFIG bitfields (datasheet Table 7-6)
    # ----------------------------
    ADC_MODE_SHIFT  = 12
    ADC_VBUSCT_SHIFT = 9
    ADC_VSHCT_SHIFT  = 6
    ADC_VTCT_SHIFT   = 3
    ADC_AVG_SHIFT    = 0

    # ----------------------------
    # LSB sizes & constants (datasheet tables + Eq.2–Eq.7)
    # ----------------------------
    # VSHUNT register LSB (Table 7-9)
    VSHUNT_LSB_RANGE0 = 312.5e-9    # 312.5 nV/LSB when ADCRANGE=0
    VSHUNT_LSB_RANGE1 = 78.125e-9   # 78.125 nV/LSB when ADCRANGE=1

    # VBUS register LSB (Table 7-10)
    VBUS_LSB = 195.3125e-6          # 195.3125 µV/LSB

    # DIETEMP register LSB (Table 7-11)
    TEMP_LSB = 7.8125e-3            # 7.8125 m°C/LSB = 0.0078125 °C/LSB

    # Shunt limit registers SOVL/SUVL LSB (Table 7-17 / 7-18)
    SHUNT_LIMIT_LSB_RANGE0 = 5e-6      # 5 µV/LSB when ADCRANGE=0
    SHUNT_LIMIT_LSB_RANGE1 = 1.25e-6   # 1.25 µV/LSB when ADCRANGE=1

    # Bus limit registers BOVL/BUVL LSB (Table 7-19 / 7-20)
    BUS_LIMIT_LSB = 3.125e-3         # 3.125 mV/LSB

    # SHUNT_CAL scaling constant (Eq. 2)
    SHUNT_CAL_SCALAR = 13107.2e6

    # Power/Energy scaling (Eq. 5 / Eq. 6)
    POWER_SCALAR = 3.2
    ENERGY_SCALAR = 16 * 3.2

    # Power limit register scaling (Table 7-22): 256 × Power LSB
    PWR_LIMIT_MULT = 256

    def __init__(self, i2c: I2C, address=INA228_ADDRESS,
                 shunt_ohms=RSHUNT_OHMS,
                 max_expected_current_a=MAX_EXPECTED_CURRENT_A,
                 adcrange=ADCRANGE):
        self._i2c = i2c
        self._address = address
        self._shunt_ohms = float(shunt_ohms)
        self._imax = float(max_expected_current_a)
        self._adcrange = int(adcrange) & 0x1

    # --------
    # Low-level I2C
    # --------
    '''
    def read_register16(self, reg: int) -> int:
        b = self._i2c.readfrom_mem(self._address, reg, 2)
        return int.from_bytes(b, 'big')

    def read_register24(self, reg: int) -> int:
        b = self._i2c.readfrom_mem(self._address, reg, 3)
        return int.from_bytes(b, 'big')

    def read_register40(self, reg: int) -> int:
        # Datasheet: ENERGY and CHARGE are 40-bit registers (Table 7-3).
        # Read 5 bytes starting at the register pointer.
        b = self._i2c.readfrom_mem(self._address, reg, 5)
        return int.from_bytes(b, 'big')

    def write_register16(self, reg: int, value: int) -> None:
        value &= 0xFFFF
        self._i2c.writeto_mem(self._address, reg, value.to_bytes(2, 'big'))
    '''
    def _read(self, reg, n):
        # Repeated-start read: write pointer without STOP, then read
        self._i2c.writeto(self._address, bytes([reg]))
        return self._i2c.readfrom(self._address, n)

    def read_register16(self, reg):
        return int.from_bytes(self._read(reg, 2), 'big')

    def read_register24(self, reg):
        return int.from_bytes(self._read(reg, 3), 'big')

    def read_register40(self, reg):
        return int.from_bytes(self._read(reg, 5), 'big')

    def write_register16(self, reg, value):
        value &= 0xFFFF
        self._i2c.writeto(self._address, bytes([reg, (value >> 8) & 0xFF, value & 0xFF]))
    # --------
    # Helpers: two's complement conversion
    # --------
    @staticmethod
    def _twos_complement(value: int, bits: int) -> int:
        # Proper sign handling: negative if MSB is 1
        if value & (1 << (bits - 1)):
            value -= (1 << bits)
        return value

    @staticmethod
    def _clamp(val: int, lo: int, hi: int) -> int:
        return lo if val < lo else hi if val > hi else val

    # --------
    # Datasheet scaling (Eq.3)
    # --------
    def current_lsb(self) -> float:
        # CURRENT_LSB = MaxExpectedCurrent / 2^19 (datasheet Eq. 3)
        return self._imax / (1 << 19)

    def shunt_cal_value(self) -> int:
        # SHUNT_CAL = 13107.2e6 * CURRENT_LSB * RSHUNT (datasheet Eq. 2)
        # For ADCRANGE=1, SHUNT_CAL must be multiplied by 4 (datasheet note under Eq. 2)
        scale = 4 if self._adcrange == 1 else 1
        cal = int(round(self.SHUNT_CAL_SCALAR * self.current_lsb() * self._shunt_ohms * scale))
        # SHUNT_CAL is 15 bits (Table 7-7: bit15 reserved)
        return self._clamp(cal, 0, 0x7FFF)

    # --------
    # Configuration
    # --------
    def reset_all(self) -> None:
        cfg = self.read_register16(self.REG_CONFIG)
        cfg |= (1 << self.CONFIG_RST_BIT)
        self.write_register16(self.REG_CONFIG, cfg)
        # RST self-clears (datasheet Table 7-5)

    def reset_energy_charge_accumulators(self) -> None:
        cfg = self.read_register16(self.REG_CONFIG)
        cfg |= (1 << self.CONFIG_RSTACC_BIT)
        self.write_register16(self.REG_CONFIG, cfg)

    def set_config(self, convdly_2ms_steps: int = 0, tempcomp_enable: bool = False) -> None:
        # CONFIG register fields (Table 7-5)
        cfg = 0
        cfg |= (convdly_2ms_steps & 0xFF) << self.CONFIG_CONVDLY_SHIFT
        cfg |= (1 if tempcomp_enable else 0) << self.CONFIG_TEMPCOMP_BIT
        cfg |= (self._adcrange & 0x1) << self.CONFIG_ADCRANGE_BIT
        self.write_register16(self.REG_CONFIG, cfg)

    def set_adc_config(self,
                       mode: int = 0xF,
                       vbusct: int = 0x05,
                       vshct: int = 0x05,
                       vtct: int = 0x05,
                       avg: int = 0x03) -> None:
        # ADC_CONFIG register fields (Table 7-6)
        adc = 0
        adc |= (mode & 0xF) << self.ADC_MODE_SHIFT
        adc |= (vbusct & 0x7) << self.ADC_VBUSCT_SHIFT
        adc |= (vshct & 0x7) << self.ADC_VSHCT_SHIFT
        adc |= (vtct & 0x7) << self.ADC_VTCT_SHIFT
        adc |= (avg & 0x7) << self.ADC_AVG_SHIFT
        self.write_register16(self.REG_ADC_CONFIG, adc)

    def set_shunt_tempco(self, tempco_ppm_per_c: int) -> None:
        # SHUNT_TEMPCO is 14-bit ppm/°C (Table 7-8)
        val = self._clamp(int(tempco_ppm_per_c), 0, 0x3FFF)
        self.write_register16(self.REG_SHUNT_TEMPCO, val)

    def program_shunt_cal(self) -> None:
        self.write_register16(self.REG_SHUNT_CAL, self.shunt_cal_value())

    def configure(self,
                  convdly_2ms_steps: int = 0,
                  tempcomp_enable: bool = False,
                  tempco_ppm_per_c: int = 0,
                  mode: int = 0xF,
                  vbusct: int = 0x05,
                  vshct: int = 0x05,
                  vtct: int = 0x05,
                  avg: int = 0x03) -> None:
        # Typical init: reset → config → adc config → shunt cal → tempco
        self.reset_all()
        time.sleep(0.01)

        self.set_config(convdly_2ms_steps=convdly_2ms_steps, tempcomp_enable=tempcomp_enable)
        time.sleep(0.01)

        self.set_adc_config(mode=mode, vbusct=vbusct, vshct=vshct, vtct=vtct, avg=avg)
        time.sleep(0.01)

        self.program_shunt_cal()
        time.sleep(0.01)

        self.set_shunt_tempco(tempco_ppm_per_c)
        time.sleep(0.01)

    # --------
    # Measurements (datasheet Tables 7-9..7-15, Eq.4..Eq.7)
    # --------
    def get_shunt_voltage_v(self) -> float:
        raw24 = self.read_register24(self.REG_VSHUNT)
        raw20 = raw24 >> 4  # bits 23-4 are data (Table 7-9)
        signed = self._twos_complement(raw20, 20)
        lsb = self.VSHUNT_LSB_RANGE0 if self._adcrange == 0 else self.VSHUNT_LSB_RANGE1
        return signed * lsb

    def get_bus_voltage_v(self) -> float:
        raw24 = self.read_register24(self.REG_VBUS)
        raw20 = raw24 >> 4  # bits 23-4 are data (Table 7-10)
        signed = self._twos_complement(raw20, 20)  # always positive per datasheet, but format is two's comp
        return signed * self.VBUS_LSB

    def get_die_temp_c(self) -> float:
        raw16 = self.read_register16(self.REG_DIETEMP)
        signed = self._twos_complement(raw16, 16)
        return signed * self.TEMP_LSB

    def get_current_a(self) -> float:
        # Current[A] = CURRENT_LSB * CURRENT (Eq. 4)
        raw24 = self.read_register24(self.REG_CURRENT)
        raw20 = raw24 >> 4  # bits 23-4 (Table 7-12)
        signed = self._twos_complement(raw20, 20)
        return signed * self.current_lsb()

    def get_power_w(self) -> float:
        # Power[W] = 3.2 * CURRENT_LSB * POWER (Eq. 5)
        raw24 = self.read_register24(self.REG_POWER)  # full 24-bit value (Table 7-13)
        return self.POWER_SCALAR * self.current_lsb() * raw24

    def get_energy_j(self) -> float:
        # Energy[J] = 16 * 3.2 * CURRENT_LSB * ENERGY (Eq. 6)
        raw40 = self.read_register40(self.REG_ENERGY)  # unsigned (Table 7-14)
        return self.ENERGY_SCALAR * self.current_lsb() * raw40

    def get_charge_c(self) -> float:
        # Charge[C] = CURRENT_LSB * CHARGE (Eq. 7)
        raw40 = self.read_register40(self.REG_CHARGE)  # two's complement (Table 7-15)
        signed = self._twos_complement(raw40, 40)
        return signed * self.current_lsb()

    # --------
    # Threshold helpers (datasheet Tables 7-17..7-22)
    # --------
    def set_bus_overvoltage_v(self, volts: float) -> None:
        code = int(round(float(volts) / self.BUS_LIMIT_LSB))
        code = self._clamp(code, 0, 0x7FFF)  # 15-bit unsigned (Tables 7-19)
        self.write_register16(self.REG_BOVL, code)

    def set_bus_undervoltage_v(self, volts: float) -> None:
        code = int(round(float(volts) / self.BUS_LIMIT_LSB))
        code = self._clamp(code, 0, 0x7FFF)  # 15-bit unsigned (Tables 7-20)
        self.write_register16(self.REG_BUVL, code)

    def set_shunt_overcurrent_a(self, amps: float) -> None:
        # SOVL compares against shunt voltage (Table 7-17).
        # Convert A -> Vshunt and then V -> register code using the SOVL LSB.
        vshunt = float(amps) * self._shunt_ohms
        lsb = self.SHUNT_LIMIT_LSB_RANGE0 if self._adcrange == 0 else self.SHUNT_LIMIT_LSB_RANGE1
        code = int(round(vshunt / lsb))
        code = self._clamp(code, -32768, 32767)
        self.write_register16(self.REG_SOVL, code & 0xFFFF)

    def set_shunt_undercurrent_a(self, amps: float) -> None:
        vshunt = float(amps) * self._shunt_ohms
        lsb = self.SHUNT_LIMIT_LSB_RANGE0 if self._adcrange == 0 else self.SHUNT_LIMIT_LSB_RANGE1
        code = int(round(vshunt / lsb))
        code = self._clamp(code, -32768, 32767)
        self.write_register16(self.REG_SUVL, code & 0xFFFF)

    def set_temp_limit_c(self, temp_c: float) -> None:
        # TEMP_LIMIT compares directly to DIETEMP format (Table 7-21).
        code = int(round(float(temp_c) / self.TEMP_LSB))
        code = self._clamp(code, -32768, 32767)
        self.write_register16(self.REG_TEMP_LIMIT, code & 0xFFFF)

    def set_power_limit_w(self, watts: float) -> None:
        # PWR_LIMIT LSB = 256 * Power_LSB (Table 7-22)
        # Power_LSB = 3.2 * CURRENT_LSB (from Eq. 5)
        power_lsb = self.POWER_SCALAR * self.current_lsb()
        limit_lsb = self.PWR_LIMIT_MULT * power_lsb
        code = int(round(float(watts) / limit_lsb))
        code = self._clamp(code, 0, 0xFFFF)
        self.write_register16(self.REG_PWR_LIMIT, code)

    # --------
    # IDs
    # --------
    def get_manufacturer_id(self) -> int:
        return self.read_register16(self.REG_MANUFACTURER_ID)

    def get_device_id(self) -> int:
        return self.read_register16(self.REG_DEVICE_ID)