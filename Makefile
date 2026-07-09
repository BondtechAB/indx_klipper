KLIPPER_SRC ?= out/klipper
BUILD_DIR ?= out/klipper-indx
INDX_CONFIG ?= bondtech_indx_usb.config

.DEFAULT_GOAL := firmware

.PHONY: firmware flash check-flash-device check-klipper-src prepare clean

firmware: check-klipper-src prepare
	$(MAKE) -C $(BUILD_DIR)

flash: check-flash-device check-klipper-src prepare
	$(MAKE) -C $(BUILD_DIR) flash FLASH_DEVICE="$(FLASH_DEVICE)"

check-flash-device:
	@test -n "$(FLASH_DEVICE)" || (echo "Set FLASH_DEVICE=/dev/serial/by-id/..." >&2; exit 2)

check-klipper-src:
	@test -f "$(KLIPPER_SRC)/Makefile" || (echo "Klipper source not found at $(KLIPPER_SRC). Run ./install.sh /path/to/klipper first." >&2; exit 2)

prepare:
	./mcu/scripts/prepare-klipper-build.py "$(KLIPPER_SRC)" "$(BUILD_DIR)" "$(INDX_CONFIG)"

clean:
	$(MAKE) -C $(BUILD_DIR) clean
