#include <string.h>
#include "config.h"
#include "esp_log.h"
#include "nvs.h"
#include "nvs_flash.h"

static const char *TAG = "inka";
#define NS "inka"

static esp_err_t read_str(nvs_handle_t h, const char *key, char *out, size_t size) {
    size_t len = size;
    esp_err_t err = nvs_get_str(h, key, out, &len);
    if (err != ESP_OK) {
        ESP_LOGE(TAG, "config missing %s (%s)", key, esp_err_to_name(err));
    }
    return err;
}

esp_err_t config_load(inka_config_t *c) {
    memset(c, 0, sizeof(*c));
    esp_err_t err = nvs_flash_init();
    if (err != ESP_OK) {
        ESP_LOGE(TAG, "nvs init failed: %s", esp_err_to_name(err));
        return err;
    }
    nvs_handle_t h;
    err = nvs_open(NS, NVS_READWRITE, &h);
    if (err != ESP_OK) {
        ESP_LOGE(TAG, "config namespace missing (%s), run tools/provision.py", esp_err_to_name(err));
        return ESP_ERR_NOT_FOUND;
    }
    esp_err_t result = ESP_OK;
    if (read_str(h, "wifi_ssid", c->ssid, sizeof(c->ssid)) != ESP_OK) result = ESP_ERR_NOT_FOUND;
    if (read_str(h, "wifi_pass", c->pass, sizeof(c->pass)) != ESP_OK) result = ESP_ERR_NOT_FOUND;
    if (read_str(h, "server_url", c->server_url, sizeof(c->server_url)) != ESP_OK) result = ESP_ERR_NOT_FOUND;
    if (read_str(h, "device_token", c->token, sizeof(c->token)) != ESP_OK) result = ESP_ERR_NOT_FOUND;
    char mode[8] = "";
    size_t len = sizeof(mode);
    c->sleep_mode = nvs_get_str(h, "sleep_mode", mode, &len) == ESP_OK ? cycle_parse_mode(mode) : CYCLE_MODE_LIGHT;
    if (c->sleep_mode == CYCLE_MODE_UNKNOWN) {
        c->sleep_mode = CYCLE_MODE_LIGHT;
    }
    nvs_close(h);
    if (result == ESP_OK) {
        ESP_LOGI(TAG, "config ok, server %s, mode %s", c->server_url, c->sleep_mode == CYCLE_MODE_DEEP ? "deep" : "light");
    }
    return result;
}

esp_err_t config_set_sleep_mode(cycle_mode_t mode) {
    nvs_handle_t h;
    esp_err_t err = nvs_open(NS, NVS_READWRITE, &h);
    if (err != ESP_OK) {
        return err;
    }
    err = nvs_set_str(h, "sleep_mode", mode == CYCLE_MODE_DEEP ? "deep" : "light");
    if (err == ESP_OK) {
        err = nvs_commit(h);
    }
    nvs_close(h);
    return err;
}
