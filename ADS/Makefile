# Reproducible build from tracked sources. Never invokes a programmer.
# CubeIDE's managed build remains available; stale ADS/Debug files are not used.
TOOLCHAIN ?= /Applications/STM32CubeIDE.app/Contents/Eclipse/plugins/com.st.stm32cube.ide.mcu.externaltools.gnu-tools-for-stm32.14.3.rel1.macosaarch64_1.0.0.202602081740/tools/bin
CC := $(if $(TOOLCHAIN),$(TOOLCHAIN)/,)arm-none-eabi-gcc
SIZE := $(if $(TOOLCHAIN),$(TOOLCHAIN)/,)arm-none-eabi-size
OUT ?= ../build/stm32-default-disabled
BENCH_PROFILE ?=
SOURCES := $(wildcard Core/Src/*.c) $(wildcard Drivers/STM32F4xx_HAL_Driver/Src/*.c)
OBJECTS := $(patsubst %.c,$(OUT)/%.o,$(SOURCES)) $(OUT)/startup.o
CPU := -mcpu=cortex-m4 -mthumb -mfpu=fpv4-sp-d16 -mfloat-abi=hard
INCLUDES := -ICore/Inc -IDrivers/STM32F4xx_HAL_Driver/Inc -IDrivers/STM32F4xx_HAL_Driver/Inc/Legacy -IDrivers/CMSIS/Include -IDrivers/CMSIS/Device/ST/STM32F4xx/Include
CFLAGS := $(CPU) -std=gnu11 -Og -g3 -Wall -Wextra -Werror -ffunction-sections -fdata-sections -DSTM32F401xE -DUSE_HAL_DRIVER $(INCLUDES)
ifneq ($(BENCH_PROFILE),)
ifeq ($(abspath $(OUT)),$(abspath ../build/stm32-default-disabled))
$(error A bench profile requires a separate OUT directory)
endif
CFLAGS += -include $(abspath $(BENCH_PROFILE))
endif
$(OUT)/Drivers/%.o: CFLAGS += -Wno-unused-parameter
.PHONY: all
all: $(OUT)/ADS.elf
	$(SIZE) $<
$(OUT)/%.o: %.c
	@mkdir -p $(dir $@)
	$(CC) $(CFLAGS) -MMD -MP -c $< -o $@
$(OUT)/startup.o: Core/Startup/startup_stm32f401retx.s
	@mkdir -p $(dir $@)
	$(CC) $(CPU) -c $< -o $@
$(OUT)/ADS.elf: $(OBJECTS) STM32F401RETX_FLASH.ld
	$(CC) $(CPU) --specs=nano.specs --specs=nosys.specs -TSTM32F401RETX_FLASH.ld -Wl,--gc-sections,-Map=$(OUT)/ADS.map $(OBJECTS) -Wl,--start-group -lc -lm -Wl,--end-group -o $@
-include $(OBJECTS:.o=.d)
