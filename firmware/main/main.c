#include <stdio.h>
#include <string.h>
#include "board.h"
#include "config.h"
#include "cycle.h"
#include "driver/gpio.h"
#include "driver/rtc_io.h"
#include "epd.h"
#include "esp_app_desc.h"
#include "esp_heap_caps.h"
#include "esp_log.h"
#include "esp_sleep.h"
#include "fb.h"
#include "framestore.h"
#include "freertos/FreeRTOS.h"
#include "freertos/queue.h"
#include "freertos/task.h"
#include "net.h"

static const char *TAG = "inka";

#define KEY_GPIO          4
#define PWR_GPIO          5
#define WIFI_TIMEOUT_MS   20000

typedef enum { EV_KEY, EV_POWER } wake_event_t;
static QueueHandle_t s_events;

#define PWR_HOLD_MS 2000  // PMIC vypíná natvrdo až po 10 s
static volatile int s_pwr_hold_ms = PWR_HOLD_MS;  // po probuzení tlačítkem PWR kratší: úloha startuje ~0,7 s po stisku

static void IRAM_ATTR on_key(void *arg) {
    BaseType_t woken = pdFALSE;
    wake_event_t ev = EV_KEY;
    xQueueSendFromISR(s_events, &ev, &woken);
    portYIELD_FROM_ISR(woken);
}

static void key_init(void) {
    gpio_config_t io = {0};
    io.pin_bit_mask = 1ULL << KEY_GPIO;
    io.mode = GPIO_MODE_INPUT;
    io.pull_up_en = GPIO_PULLUP_ENABLE;
    io.intr_type = GPIO_INTR_NEGEDGE;
    ESP_ERROR_CHECK(gpio_config(&io));
    ESP_ERROR_CHECK(gpio_install_isr_service(0));
    ESP_ERROR_CHECK(gpio_isr_handler_add(KEY_GPIO, on_key, NULL));
}

// Podržení PWR 2 s: hned zabliká červená LED (uživatel ví, že může pustit) a pošle EV_POWER.
static void power_key_task(void *arg) {
    int held_ms = 0;
    for (;;) {
        held_ms = board_pwr_pressed() ? held_ms + 50 : 0;
        if (held_ms == s_pwr_hold_ms) {
            ESP_LOGI(TAG, "power button held");
            // Událost hned: hlavní smyčka nesmí po puštění tlačítka usoudit, že šlo o krátký stisk.
            wake_event_t ev = EV_POWER;
            xQueueSend(s_events, &ev, portMAX_DELAY);
            for (int i = 0; i < 3; i++) {
                board_led(BOARD_LED_RED, true);
                vTaskDelay(pdMS_TO_TICKS(150));
                board_led(BOARD_LED_RED, false);
                vTaskDelay(pdMS_TO_TICKS(150));
            }
            board_led(BOARD_LED_RED, true);  // svítí, dokud se nevypne
            vTaskDelete(NULL);
        }
        vTaskDelay(pdMS_TO_TICKS(50));
    }
}

// Čeká na časovač, KEY nebo PWR. Stisky KEY z doby překreslení zahodí, PWR nikdy.
static wake_event_t wait_for_wake(int seconds, const char **wake) {
    wake_event_t ev;
    while (xQueueReceive(s_events, &ev, 0) == pdTRUE) {
        if (ev == EV_POWER) {
            return EV_POWER;
        }
    }
    // pdMS_TO_TICKS by u týdenního spánku přetekl
    TickType_t ticks = (TickType_t)seconds * configTICK_RATE_HZ;
    if (xQueueReceive(s_events, &ev, ticks) == pdTRUE) {
        if (ev == EV_POWER) {
            return EV_POWER;
        }
        vTaskDelay(pdMS_TO_TICKS(50));
        *wake = "button";
        return EV_KEY;
    }
    *wake = "timer";
    return EV_KEY;
}

static bool show(const uint8_t *buf) {
    esp_err_t err = epd_init();
    if (err == ESP_OK) {
        err = epd_show(buf);
    }
    if (err == ESP_OK) {
        epd_sleep();
        return true;
    }
    ESP_LOGE(TAG, "display failed: %s", esp_err_to_name(err));
    return false;
}

// Stav cyklu, který musí přežít hluboký spánek.
#define RTC_MAGIC 0x494E4B41u
typedef struct {
    uint32_t magic;
    char     etag[48];
    int      interval;
    int      failures;
    int      portrait;
    int      rot180;
} rtc_state_t;
RTC_DATA_ATTR static rtc_state_t s_rtc;

// Vypnutí tlačítkem PWR: do posledního zobrazeného obrazu dokreslí štítek OFF, překreslí a vypne PMIC.
// Obraz bere z RAM, a když tam není (po hlubokém spánku), z oddílu „frame“.
static void power_off(uint8_t *buf, const uint8_t *shown) {
    ESP_LOGI(TAG, "shutting down");
    int portrait = s_rtc.portrait, rot180 = s_rtc.rot180;
    bool have = shown != NULL;
    if (have) {
        memcpy(buf, shown, FB_LEN);
    } else {
        have = framestore_load(buf, &portrait, &rot180) == ESP_OK;
    }
    if (have && portrait >= 0) {
        fb_draw_off_badge(buf, portrait, rot180);
        show(buf);
    } else {
        ESP_LOGW(TAG, "no stored frame, powering off without badge");
    }
    board_led(BOARD_LED_RED, false);
    board_power_off();
    for (;;) {
        vTaskDelay(portMAX_DELAY);  // bez PMIC zůstat stát
    }
}

static void deep_sleep(int seconds) {
    board_prepare_deep_sleep();
    esp_sleep_enable_timer_wakeup((uint64_t)seconds * 1000000ULL);
    rtc_gpio_pullup_en(KEY_GPIO);  // KEY: stisk = log. 0
    rtc_gpio_pulldown_dis(KEY_GPIO);
    esp_sleep_enable_ext1_wakeup_io(1ULL << KEY_GPIO, ESP_EXT1_WAKEUP_ANY_LOW);
    rtc_gpio_pullup_dis(PWR_GPIO);  // PWR: stisk = log. 1
    rtc_gpio_pulldown_en(PWR_GPIO);
    esp_sleep_enable_ext0_wakeup(PWR_GPIO, 1);
    ESP_LOGI(TAG, "deep sleep %d s", seconds);
    vTaskDelay(pdMS_TO_TICKS(50));  // dopsat log
    esp_deep_sleep_start();
}

static const char *wake_from_cause(esp_sleep_wakeup_cause_t cause) {
    switch (cause) {
    case ESP_SLEEP_WAKEUP_TIMER: return "timer";
    case ESP_SLEEP_WAKEUP_EXT1:  return "button";  // KEY
    case ESP_SLEEP_WAKEUP_EXT0:  return "button";  // PWR krátce; dlouhý stisk řeší power_key_task
    default:                     return "boot";
    }
}

void app_main(void) {
    const char *fw = esp_app_get_description()->version;
    esp_sleep_wakeup_cause_t cause = esp_sleep_get_wakeup_cause();
    const char *wake = wake_from_cause(cause);
    if (cause == ESP_SLEEP_WAKEUP_UNDEFINED || s_rtc.magic != RTC_MAGIC) {
        memset(&s_rtc, 0, sizeof(s_rtc));
        s_rtc.magic = RTC_MAGIC;
        s_rtc.interval = CYCLE_DEFAULT_INTERVAL_S;
        s_rtc.portrait = -1;
        s_rtc.rot180 = -1;
    }
    ESP_LOGI(TAG, "boot, fw %s, wake %s", fw, wake);

    if (board_init() != ESP_OK) {
        ESP_LOGW(TAG, "continuing without pmic");
    }
    if (cause != ESP_SLEEP_WAKEUP_UNDEFINED) {
        rtc_gpio_deinit(KEY_GPIO);  // vrátit piny z RTC domény do běžné GPIO
        rtc_gpio_deinit(PWR_GPIO);
    }
    uint8_t *buf = heap_caps_malloc(FB_LEN, MALLOC_CAP_SPIRAM);
    uint8_t *shown = heap_caps_malloc(FB_LEN, MALLOC_CAP_SPIRAM);  // poslední zobrazený obraz (pro štítek OFF)
    inka_config_t cfg;
    if (buf == NULL || shown == NULL || config_load(&cfg) != ESP_OK) {
        ESP_LOGE(TAG, "%s", buf == NULL || shown == NULL ? "fb alloc failed" : "not provisioned");
        board_led(BOARD_LED_RED, true);
        return;
    }
    s_events = xQueueCreate(4, sizeof(wake_event_t));
    net_wifi_init();
    key_init();
    if (cause == ESP_SLEEP_WAKEUP_EXT0) {
        s_pwr_hold_ms = 1300;
    }
    xTaskCreate(power_key_task, "pwr_key", 3072, NULL, 5, NULL);

    if (cause == ESP_SLEEP_WAKEUP_EXT0) {
        // Probuzení tlačítkem PWR: dokud ho uživatel drží, čekat na rozhodnutí power_key_task (vypnutí),
        // jinak hned pokračovat. Úloha startuje až po bootu, proto se nečeká pevně dlouho.
        wake_event_t ev;
        int released = 0;
        for (int waited = 0; waited < 4000 && released < 3; waited += 50) {  // 3 vzorky = 150 ms proti zákmitům
            if (xQueueReceive(s_events, &ev, pdMS_TO_TICKS(50)) == pdTRUE && ev == EV_POWER) {
                power_off(buf, NULL);
            }
            released = board_pwr_pressed() ? 0 : released + 1;
        }
        s_pwr_hold_ms = PWR_HOLD_MS;
    }

    bool have_shown = false;
    bool frame_dirty = false;  // zobrazený obraz ještě není v oddílu „frame“
    char query[200];
    char url[sizeof(cfg.server_url) + 32 + sizeof(query)];

    for (;;) {
        board_led(BOARD_LED_GREEN, true);
        int pct = board_battery_percent();
        cycle_report_t report = {board_battery_mv(), pct, pct >= 0 ? board_is_charging() : -1, board_temperature_c10(),
                                 board_usb_powered() ? 1 : 0};
        cycle_build_query(query, sizeof(query), &report, fw, wake);
        snprintf(url, sizeof(url), "%s/api/v1/frame%s", cfg.server_url, query);

        net_frame_t res = {0};
        esp_err_t err = net_wifi_connect(cfg.ssid, cfg.pass, WIFI_TIMEOUT_MS);
        if (err == ESP_OK) {
            err = net_fetch_frame(url, cfg.token, s_rtc.etag, buf, FB_LEN, &res);
        }
        net_wifi_disconnect();

        bool ok = err == ESP_OK && (res.status == 200 || res.status == 204 || res.status == 304);
        if (ok && res.status == 200) {
            if (res.len != FB_LEN) {
                ESP_LOGE(TAG, "bad frame length %u", (unsigned)res.len);
                ok = false;
            } else if (show(buf)) {
                strlcpy(s_rtc.etag, res.etag, sizeof(s_rtc.etag));
                memcpy(shown, buf, FB_LEN);
                have_shown = true;
                frame_dirty = true;
                if (res.portrait >= 0) {
                    s_rtc.portrait = res.portrait;
                    s_rtc.rot180 = res.rot180;
                }
            } else {
                ok = false;
            }
        }
        ESP_LOGI(TAG, "fetch status %d, err %s", res.status, esp_err_to_name(err));
        if (ok && res.status == 304) {
            ESP_LOGI(TAG, "not modified");
        }
        if (ok && res.status == 204) {
            ESP_LOGI(TAG, "no photos on server");
        }

        int sleep_s;
        if (ok) {
            s_rtc.failures = 0;
            if (res.interval_s > 0) {
                s_rtc.interval = res.interval_s;
            }
            sleep_s = res.sleep_s > 0 ? res.sleep_s : s_rtc.interval;
            if (res.sleep_mode != CYCLE_MODE_UNKNOWN && res.sleep_mode != cfg.sleep_mode) {
                cfg.sleep_mode = res.sleep_mode;
                config_set_sleep_mode(res.sleep_mode);
                ESP_LOGI(TAG, "sleep mode -> %s", res.sleep_mode == CYCLE_MODE_DEEP ? "deep" : "light");
            }
        } else {
            s_rtc.failures++;
            sleep_s = cycle_retry_delay_s(s_rtc.failures, s_rtc.interval);
        }
        board_led(BOARD_LED_GREEN, false);
        ESP_LOGI(TAG, "sleep %d s (interval %d, failures %d, mode %s)", sleep_s, s_rtc.interval, s_rtc.failures,
                 cfg.sleep_mode == CYCLE_MODE_DEEP ? "deep" : "light");

        if (cfg.sleep_mode == CYCLE_MODE_DEEP) {
            // Stisky během cyklu: PWR vypíná. KEY se zahodí jako v lehkém spánku – uvolnění tlačítka,
            // které rámeček probudilo, zakmitá a jinak by spustilo druhý cyklus a přeskočilo fotku.
            wake_event_t ev;
            while (xQueueReceive(s_events, &ev, 0) == pdTRUE) {
                if (ev == EV_POWER) {
                    power_off(buf, have_shown ? shown : NULL);
                }
            }
            if (frame_dirty) {
                framestore_save(shown, s_rtc.portrait, s_rtc.rot180);
                frame_dirty = false;
            }
            deep_sleep(sleep_s);
        }
        if (wait_for_wake(sleep_s, &wake) == EV_POWER) {
            power_off(buf, have_shown ? shown : NULL);
        }
        ESP_LOGI(TAG, "wake %s", wake);
    }
}
