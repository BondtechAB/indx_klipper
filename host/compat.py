from klippy.configfile import ConfigWrapper as RealConfigWrapper
from klippy.configfile import error as ConfigError


class ConfigWrapper(RealConfigWrapper):
    def __init__(self, printer, name, contents, fallback=None):
        self.section = name
        self.printer = printer
        self.fileconfig = ConfigContents(name, contents, fallback)
        self.access_tracking = {}


class ConfigContents:
    def __init__(self, section, contents, fallback):
        self.section = section
        self.contents = contents
        self.fallback = fallback

    def has_option(self, section, option):
        if section != self.section:
            return False
        return option in self.contents

    def sections(self):
        return [self.section]

    def getsection(self, _section):
        return self

    def get(self, section, option):
        if not self.has_option(section, option):
            if self.fallback:
                return self.fallback.get(section, option)
            raise ConfigError(f"missing option {section}:{option}")
        return self.contents[option]

    def get_converted(self, section, option, conv):
        return conv(self.get(section, option))

    def getint(self, section, option):
        return self.get_converted(section, option, int)

    def getfloat(self, section, option):
        return self.get_converted(section, option, float)

    def getboolean(self, section, option):
        return self.get_converted(section, option, bool)


def register_response(mcu, callback, msgformat):
    """
    Register an MCU response handler, returning a handle with .unregister().
    Compatibility layer for Kalico and Klipper.
    """
    try:
        register = mcu.register_response  # Kalico + old Klipper
    except AttributeError:
        return mcu.register_serial_response(callback, msgformat)  # New Klipper
    name = msgformat.split()[0]
    register(callback, name)
    return _ResponseHandle(mcu, name)


class _ResponseHandle:
    def __init__(self, mcu, name):
        self._mcu = mcu
        self._name = name

    def unregister(self):
        self._mcu.register_response(None, self._name)


def register_adc_callback(adc, callback):
    """
    Register ADC callback. Compatibility layer for Kalico and Klipper.
    """
    if hasattr(adc, "setup_adc_sample"):
        # New Klipper ADC callback style
        adc.setup_adc_callback(
            lambda samples: callback(samples[-1][0], samples[-1][1])
        )
        adc.setup_adc_sample(0.3, 0.001, 8)
    else:
        # Old klipper and Kalico ADC callback style
        adc.setup_adc_callback(0.3, callback)
        adc.setup_minmax(0.001, 8)
