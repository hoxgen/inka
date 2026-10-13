// Deska PhotoPainter: piny a nastavení PMIC podle pmicpower, i2c_bsp a led_bsp z příkladu Waveshare
// ESP32-S3-PhotoPainter (01_Example/xiaozhi-esp32, licence MIT). Ovladač AXP2101: XPowersLib (xpowers/, MIT).
#include <climits>
#include "board.h"
#include "driver/gpio.h"
#include "driver/i2c_master.h"
#include "esp_log.h"
#include "esp_rom_sys.h"
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"
#include "XPowersLib.h"

static const char *TAG = "inka";

#define I2C_PORT_NUM  0
#define I2C_SCL       48
#define I2C_SDA       47
#define PMIC_ADDR     0x34
#define LED_RED_GPIO  45
#define LED_GREEN_GPIO 42
#define PWR_KEY_GPIO  5
#define SHTC3_ADDR    0x70

static i2c_master_bus_handle_t s_bus;
static i2c_master_dev_handle_t s_pmic_dev;
static i2c_master_dev_handle_t s_shtc3_dev;
static XPowersPMU s_pmic;
static bool s_pmic_ok;

static int pmic_read(uint8_t, uint8_t reg, uint8_t *data, uint8_t len) {
    for (int attempt = 0; attempt < 3; attempt++) {
        if (i2c_master_transmit_receive(s_pmic_dev, &reg, 1, data, len, 1000) == ESP_OK) {
            return 0;
        }
        vTaskDelay(pdMS_TO_TICKS(100));
    }
    return -1;
}

static int pmic_write(uint8_t, uint8_t reg, uint8_t *data, uint8_t len) {
    uint8_t tmp[16];
    if (len + 1 > (int)sizeof(tmp)) {
        return -1;
    }
    tmp[0] = reg;
    for (int i = 0; i < len; i++) {
        tmp[i + 1] = data[i];
    }
    for (int attempt = 0; attempt < 3; attempt++) {
        if (i2c_master_transmit(s_pmic_dev, tmp, len + 1, 1000) == ESP_OK) {
            return 0;
        }
        vTaskDelay(pdMS_TO_TICKS(100));
    }
    return -1;
}

static void leds_init(void) {
    gpio_config_t io = {};
    io.pin_bit_mask = (1ULL << LED_RED_GPIO) | (1ULL << LED_GREEN_GPIO);
    io.mode = GPIO_MODE_OUTPUT;
    gpio_config(&io);
    board_led(BOARD_LED_RED, false);
    board_led(BOARD_LED_GREEN, false);
}

static void pmic_configure(void) {
    s_pmic.setVbusCurrentLimit(XPOWERS_AXP2101_VBUS_CUR_LIM_2000MA);
    s_pmic.setDC1Voltage(3300);
    s_pmic.setALDO1Voltage(3300);
    s_pmic.setALDO2Voltage(3300);
    s_pmic.setALDO3Voltage(3300);
    s_pmic.setALDO4Voltage(3300);
    s_pmic.setPrechargeCurr(XPOWERS_AXP2101_PRECHARGE_50MA);
    s_pmic.setChargerConstantCurr(XPOWERS_AXP2101_CHG_CUR_500MA);
    s_pmic.setChargerTerminationCurr(XPOWERS_AXP2101_CHG_ITERM_25MA);
    // Hardwarové vypnutí podržením PWR jen jako záloha; firmware reaguje po 2 s a vypne sám.
    s_pmic.setPowerKeyPressOffTime(XPOWERS_POWEROFF_10S);
}

extern "C" esp_err_t board_init(void) {
    i2c_master_bus_config_t bus_cfg = {};
    bus_cfg.clk_source = I2C_CLK_SRC_DEFAULT;
    bus_cfg.i2c_port = (i2c_port_t)I2C_PORT_NUM;
    bus_cfg.scl_io_num = (gpio_num_t)I2C_SCL;
    bus_cfg.sda_io_num = (gpio_num_t)I2C_SDA;
    bus_cfg.glitch_ignore_cnt = 7;
    bus_cfg.flags.enable_internal_pullup = true;
    ESP_ERROR_CHECK(i2c_new_master_bus(&bus_cfg, &s_bus));

    i2c_device_config_t dev_cfg = {};
    dev_cfg.dev_addr_length = I2C_ADDR_BIT_LEN_7;
    dev_cfg.device_address = PMIC_ADDR;
    dev_cfg.scl_speed_hz = 100000;
    ESP_ERROR_CHECK(i2c_master_bus_add_device(s_bus, &dev_cfg, &s_pmic_dev));

    // Po probuzení z hlubokého spánku jsou LED piny ještě podržené.
    gpio_hold_dis((gpio_num_t)LED_RED_GPIO);
    gpio_hold_dis((gpio_num_t)LED_GREEN_GPIO);
    leds_init();
    i2c_device_config_t shtc3_cfg = {};
    shtc3_cfg.dev_addr_length = I2C_ADDR_BIT_LEN_7;
    shtc3_cfg.device_address = SHTC3_ADDR;
    shtc3_cfg.scl_speed_hz = 100000;
    if (i2c_master_bus_add_device(s_bus, &shtc3_cfg, &s_shtc3_dev) != ESP_OK) {
        s_shtc3_dev = NULL;
    }
    gpio_config_t key = {};
    key.pin_bit_mask = 1ULL << PWR_KEY_GPIO;
    key.mode = GPIO_MODE_INPUT;
    gpio_config(&key);

    s_pmic_ok = s_pmic.begin(PMIC_ADDR, pmic_read, pmic_write);
    if (!s_pmic_ok) {
        ESP_LOGE(TAG, "pmic init failed");
        return ESP_FAIL;
    }
    pmic_configure();
    ESP_LOGI(TAG, "pmic ok, battery %d mV, charging %d", board_battery_mv(), board_is_charging());
    return ESP_OK;
}

extern "C" int board_battery_mv(void) {
    return s_pmic_ok ? (int)s_pmic.getBattVoltage() : -1;
}

extern "C" bool board_is_charging(void) {
    return s_pmic_ok && s_pmic.isCharging();
}

extern "C" void board_led(board_led_t led, bool on) {
    gpio_set_level((gpio_num_t)(led == BOARD_LED_RED ? LED_RED_GPIO : LED_GREEN_GPIO), on ? 0 : 1);
}

extern "C" bool board_pwr_pressed(void) {
    return gpio_get_level((gpio_num_t)PWR_KEY_GPIO) == 1;
}

extern "C" void board_power_off(void) {
    ESP_LOGI(TAG, "power off");
    vTaskDelay(pdMS_TO_TICKS(100));  // dopsat log
    if (s_pmic_ok) {
        s_pmic.shutdown();
    }
}

extern "C" int board_battery_percent(void) {
    if (!s_pmic_ok || !s_pmic.isBatteryConnect()) {
        return -1;
    }
    return s_pmic.getBatteryPercent();
}

static uint8_t shtc3_crc(const uint8_t *data, int len) {
    uint8_t crc = 0xFF;
    for (int i = 0; i < len; i++) {
        crc ^= data[i];
        for (int b = 0; b < 8; b++) {
            crc = (crc & 0x80) ? (uint8_t)((crc << 1) ^ 0x31) : (uint8_t)(crc << 1);
        }
    }
    return crc;
}

static esp_err_t shtc3_cmd(uint16_t cmd) {
    uint8_t buf[2] = {(uint8_t)(cmd >> 8), (uint8_t)(cmd & 0xFF)};
    return i2c_master_transmit(s_shtc3_dev, buf, 2, 100);
}

extern "C" int board_temperature_c10(void) {
    if (s_shtc3_dev == NULL) {
        return INT_MIN;
    }
    uint8_t rx[6] = {0};
    const char *step = "wakeup";
    esp_err_t err = shtc3_cmd(0x3517);  // probudit
    if (err == ESP_OK) {
        esp_rom_delay_us(500);  // probuzení trvá až 240 µs; pdMS_TO_TICKS(1) je při 100 Hz nula
        step = "measure";
        err = shtc3_cmd(0x7866);  // měřit, nejdřív T, bez clock stretching
    }
    if (err == ESP_OK) {
        vTaskDelay(pdMS_TO_TICKS(30));  // 3 ticky = aspoň 20 ms; měření trvá až 12,1 ms
        step = "read";
        err = i2c_master_receive(s_shtc3_dev, rx, sizeof(rx), 100);
    }
    shtc3_cmd(0xB098);  // uspat
    if (err != ESP_OK || shtc3_crc(rx, 2) != rx[2]) {
        ESP_LOGW(TAG, "shtc3 read failed at %s: %s, data %02x%02x crc %02x/%02x", step, esp_err_to_name(err),
                 rx[0], rx[1], rx[2], shtc3_crc(rx, 2));
        return INT_MIN;
    }
    int raw = (rx[0] << 8) | rx[1];
    return -450 + (1750 * raw) / 65536;
}

extern "C" void board_prepare_deep_sleep(void) {
    board_led(BOARD_LED_RED, false);
    board_led(BOARD_LED_GREEN, false);
    gpio_hold_en((gpio_num_t)LED_RED_GPIO);
    gpio_hold_en((gpio_num_t)LED_GREEN_GPIO);
#if !SOC_GPIO_SUPPORT_HOLD_SINGLE_IO_IN_DSLP
    gpio_deep_sleep_hold_en();
#endif
}

extern "C" bool board_usb_powered(void) {
    return s_pmic_ok && s_pmic.isVbusIn();
}
