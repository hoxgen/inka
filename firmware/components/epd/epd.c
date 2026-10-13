// Ovladač 7,3" Spectra 6: piny a inicializační sekvence podle display_bsp z příkladu Waveshare
// ESP32-S3-PhotoPainter (01_Example/xiaozhi-esp32, licence MIT, (c) 2025 Shenzhen Xinzhi Future Technology).
#include <string.h>
#include "driver/gpio.h"
#include "driver/spi_master.h"
#include "esp_log.h"
#include "esp_timer.h"
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"
#include "epd.h"
#include "fb.h"

static const char *TAG = "inka";

#define PIN_MOSI 11
#define PIN_SCK  10
#define PIN_DC   8
#define PIN_CS   9
#define PIN_RST  12
#define PIN_BUSY 13
#define EPD_HOST SPI3_HOST
#define CHUNK    4096
#define BUSY_TIMEOUT_US (60LL * 1000 * 1000)
#define BUSY_ASSERT_TIMEOUT_US (500LL * 1000)

static spi_device_handle_t s_spi;
static bool s_bus_ready;

static void spi_write(const uint8_t *data, size_t len) {
    spi_transaction_t t = {0};
    t.length = len * 8;
    t.tx_buffer = data;
    ESP_ERROR_CHECK(spi_device_polling_transmit(s_spi, &t));
}

static void send_cmd(uint8_t cmd) {
    gpio_set_level(PIN_DC, 0);
    gpio_set_level(PIN_CS, 0);
    spi_write(&cmd, 1);
    gpio_set_level(PIN_CS, 1);
}

static void send_data(const uint8_t *data, size_t len) {
    gpio_set_level(PIN_DC, 1);
    gpio_set_level(PIN_CS, 0);
    while (len > 0) {
        size_t n = len > CHUNK ? CHUNK : len;
        spi_write(data, n);
        data += n;
        len -= n;
    }
    gpio_set_level(PIN_CS, 1);
}

#define CMD(c, ...) do { \
    static const uint8_t _d[] = {__VA_ARGS__}; \
    send_cmd(c); \
    send_data(_d, sizeof(_d)); \
} while (0)

static esp_err_t wait_busy(const char *what) {
    int64_t start = esp_timer_get_time();
    while (gpio_get_level(PIN_BUSY) == 0) {
        if (esp_timer_get_time() - start > BUSY_TIMEOUT_US) {
            ESP_LOGE(TAG, "epd busy timeout after %s", what);
            return ESP_ERR_TIMEOUT;
        }
        vTaskDelay(pdMS_TO_TICKS(10));
    }
    ESP_LOGD(TAG, "epd %s done in %lld ms", what, (esp_timer_get_time() - start) / 1000);
    return ESP_OK;
}

// Bez panelu drží pull-up BUSY trvale v log. 1 a wait_busy by hlásil úspěch.
// Po startu refreshe musí panel BUSY stáhnout do 0.
static esp_err_t wait_busy_asserted(const char *what) {
    int64_t start = esp_timer_get_time();
    while (gpio_get_level(PIN_BUSY) == 1) {
        if (esp_timer_get_time() - start > BUSY_ASSERT_TIMEOUT_US) {
            ESP_LOGE(TAG, "epd busy never asserted after %s (panel disconnected?)", what);
            return ESP_ERR_INVALID_RESPONSE;
        }
        vTaskDelay(pdMS_TO_TICKS(1));
    }
    return ESP_OK;
}

// Při chybě nesmí zůstat zapnuté vysoké napětí panelu.
static void power_off_best_effort(void) {
    CMD(0x02, 0x00);
    vTaskDelay(pdMS_TO_TICKS(100));
    CMD(0x07, 0xA5);
    ESP_LOGW(TAG, "epd forced power off + sleep");
}

static void reset_panel(void) {
    gpio_set_level(PIN_RST, 1);
    vTaskDelay(pdMS_TO_TICKS(50));
    gpio_set_level(PIN_RST, 0);
    vTaskDelay(pdMS_TO_TICKS(20));
    gpio_set_level(PIN_RST, 1);
    vTaskDelay(pdMS_TO_TICKS(50));
}

static void bus_init(void) {
    spi_bus_config_t bus = {0};
    bus.mosi_io_num = PIN_MOSI;
    bus.miso_io_num = -1;
    bus.sclk_io_num = PIN_SCK;
    bus.quadwp_io_num = -1;
    bus.quadhd_io_num = -1;
    bus.max_transfer_sz = CHUNK;
    ESP_ERROR_CHECK(spi_bus_initialize(EPD_HOST, &bus, SPI_DMA_CH_AUTO));

    spi_device_interface_config_t dev = {0};
    dev.clock_speed_hz = 40 * 1000 * 1000;
    dev.mode = 0;
    dev.spics_io_num = -1;
    dev.queue_size = 1;
    dev.flags = SPI_DEVICE_HALFDUPLEX;
    ESP_ERROR_CHECK(spi_bus_add_device(EPD_HOST, &dev, &s_spi));

    gpio_config_t out = {0};
    out.pin_bit_mask = (1ULL << PIN_RST) | (1ULL << PIN_DC) | (1ULL << PIN_CS);
    out.mode = GPIO_MODE_OUTPUT;
    out.pull_up_en = GPIO_PULLUP_ENABLE;
    ESP_ERROR_CHECK(gpio_config(&out));

    gpio_config_t in = {0};
    in.pin_bit_mask = 1ULL << PIN_BUSY;
    in.mode = GPIO_MODE_INPUT;
    in.pull_up_en = GPIO_PULLUP_ENABLE;
    ESP_ERROR_CHECK(gpio_config(&in));

    gpio_set_level(PIN_CS, 1);
    s_bus_ready = true;
}

esp_err_t epd_init(void) {
    if (!s_bus_ready) {
        bus_init();
    }
    reset_panel();
    esp_err_t err = wait_busy("reset");
    if (err != ESP_OK) {
        return err;
    }
    vTaskDelay(pdMS_TO_TICKS(50));

    CMD(0xAA, 0x49, 0x55, 0x20, 0x08, 0x09, 0x18);
    CMD(0x01, 0x3F);
    CMD(0x00, 0x5F, 0x69);
    CMD(0x03, 0x00, 0x54, 0x00, 0x44);
    CMD(0x05, 0x40, 0x1F, 0x1F, 0x2C);
    CMD(0x06, 0x6F, 0x1F, 0x17, 0x49);
    CMD(0x08, 0x6F, 0x1F, 0x1F, 0x22);
    CMD(0x30, 0x03);
    CMD(0x50, 0x3F);
    CMD(0x60, 0x02, 0x00);
    CMD(0x61, 0x03, 0x20, 0x01, 0xE0);
    CMD(0x84, 0x01);
    CMD(0xE3, 0x2F);

    send_cmd(0x04);
    err = wait_busy("power on");
    if (err == ESP_OK) {
        ESP_LOGI(TAG, "epd init ok");
    }
    return err;
}

esp_err_t epd_show(const uint8_t *buf) {
    int64_t start = esp_timer_get_time();
    send_cmd(0x10);
    send_data(buf, FB_LEN);

    send_cmd(0x04);
    esp_err_t err = wait_busy("power on");
    if (err != ESP_OK) {
        power_off_best_effort();
        return err;
    }
    CMD(0x06, 0x6F, 0x1F, 0x17, 0x49);
    CMD(0x12, 0x00);
    err = wait_busy_asserted("refresh");
    if (err == ESP_OK) {
        err = wait_busy("refresh");
    }
    if (err != ESP_OK) {
        power_off_best_effort();
        return err;
    }
    CMD(0x02, 0x00);
    err = wait_busy("power off");
    if (err == ESP_OK) {
        ESP_LOGI(TAG, "refresh done in %lld ms", (esp_timer_get_time() - start) / 1000);
    }
    return err;
}

void epd_sleep(void) {
    CMD(0x07, 0xA5);
    ESP_LOGI(TAG, "epd sleep");
}
