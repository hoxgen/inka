#include <stdio.h>
#include <string.h>
#include <strings.h>
#include "esp_crt_bundle.h"
#include "esp_event.h"
#include "esp_http_client.h"
#include "esp_log.h"
#include "esp_netif.h"
#include "esp_wifi.h"
#include "freertos/FreeRTOS.h"
#include "freertos/event_groups.h"
#include "net.h"

static const char *TAG = "inka";
#define GOT_IP_BIT BIT0

static EventGroupHandle_t s_events;
static volatile bool s_connecting;

static void on_wifi(void *arg, esp_event_base_t base, int32_t id, void *data) {
    if (base == WIFI_EVENT && id == WIFI_EVENT_STA_START && s_connecting) {
        esp_wifi_connect();
    } else if (base == WIFI_EVENT && id == WIFI_EVENT_STA_DISCONNECTED) {
        xEventGroupClearBits(s_events, GOT_IP_BIT);
        if (s_connecting) {
            esp_wifi_connect();
        }
    } else if (base == IP_EVENT && id == IP_EVENT_STA_GOT_IP) {
        ip_event_got_ip_t *ev = (ip_event_got_ip_t *)data;
        ESP_LOGI(TAG, "wifi ip " IPSTR, IP2STR(&ev->ip_info.ip));
        xEventGroupSetBits(s_events, GOT_IP_BIT);
    }
}

esp_err_t net_wifi_init(void) {
    s_events = xEventGroupCreate();
    ESP_ERROR_CHECK(esp_netif_init());
    ESP_ERROR_CHECK(esp_event_loop_create_default());
    esp_netif_create_default_wifi_sta();
    wifi_init_config_t cfg = WIFI_INIT_CONFIG_DEFAULT();
    ESP_ERROR_CHECK(esp_wifi_init(&cfg));
    ESP_ERROR_CHECK(esp_event_handler_register(WIFI_EVENT, ESP_EVENT_ANY_ID, on_wifi, NULL));
    ESP_ERROR_CHECK(esp_event_handler_register(IP_EVENT, IP_EVENT_STA_GOT_IP, on_wifi, NULL));
    ESP_ERROR_CHECK(esp_wifi_set_storage(WIFI_STORAGE_RAM));
    ESP_ERROR_CHECK(esp_wifi_set_mode(WIFI_MODE_STA));
    return ESP_OK;
}

esp_err_t net_wifi_connect(const char *ssid, const char *pass, int timeout_ms) {
    wifi_config_t wc = {0};
    strlcpy((char *)wc.sta.ssid, ssid, sizeof(wc.sta.ssid));
    strlcpy((char *)wc.sta.password, pass, sizeof(wc.sta.password));
    // Nepřipojit se k otevřené síti se stejným SSID (evil twin by viděl token).
    wc.sta.threshold.authmode = pass[0] != '\0' ? WIFI_AUTH_WPA2_PSK : WIFI_AUTH_OPEN;
    ESP_ERROR_CHECK(esp_wifi_set_config(WIFI_IF_STA, &wc));
    xEventGroupClearBits(s_events, GOT_IP_BIT);
    s_connecting = true;
    ESP_ERROR_CHECK(esp_wifi_start());
    EventBits_t bits = xEventGroupWaitBits(s_events, GOT_IP_BIT, pdFALSE, pdTRUE, pdMS_TO_TICKS(timeout_ms));
    if (!(bits & GOT_IP_BIT)) {
        ESP_LOGE(TAG, "wifi connect timeout after %d ms", timeout_ms);
        return ESP_ERR_TIMEOUT;
    }
    return ESP_OK;
}

void net_wifi_disconnect(void) {
    s_connecting = false;
    esp_wifi_disconnect();
    esp_wifi_stop();
}

static esp_err_t on_http(esp_http_client_event_t *e) {
    net_frame_t *res = (net_frame_t *)e->user_data;
    if (e->event_id != HTTP_EVENT_ON_HEADER) {
        return ESP_OK;
    }
    if (strcasecmp(e->header_key, "ETag") == 0) {
        strlcpy(res->etag, e->header_value, sizeof(res->etag));
    } else if (strcasecmp(e->header_key, "X-Inka-Sleep-Seconds") == 0) {
        res->sleep_s = cycle_parse_sleep_s(e->header_value, -1);
    } else if (strcasecmp(e->header_key, "X-Inka-Interval-Seconds") == 0) {
        res->interval_s = cycle_parse_sleep_s(e->header_value, -1);
    } else if (strcasecmp(e->header_key, "X-Inka-View") == 0) {
        cycle_parse_view(e->header_value, &res->portrait, &res->rot180);
    } else if (strcasecmp(e->header_key, "X-Inka-Sleep-Mode") == 0) {
        res->sleep_mode = cycle_parse_mode(e->header_value);
    }
    return ESP_OK;
}

esp_err_t net_fetch_frame(const char *url, const char *token, const char *etag,
                          uint8_t *buf, size_t cap, net_frame_t *res) {
    memset(res, 0, sizeof(*res));
    res->sleep_s = -1;
    res->interval_s = -1;
    res->portrait = -1;
    res->rot180 = -1;
    res->sleep_mode = CYCLE_MODE_UNKNOWN;

    esp_http_client_config_t cfg = {
        .url = url,
        .event_handler = on_http,
        .user_data = res,
        .timeout_ms = 15000,
        .crt_bundle_attach = esp_crt_bundle_attach,
        .buffer_size = 4096,
    };
    esp_http_client_handle_t client = esp_http_client_init(&cfg);
    if (client == NULL) {
        return ESP_FAIL;
    }
    char auth[96];
    snprintf(auth, sizeof(auth), "Bearer %s", token);
    esp_http_client_set_header(client, "Authorization", auth);
    esp_http_client_set_header(client, "Accept-Encoding", "identity");
    if (etag != NULL && etag[0] != '\0') {
        esp_http_client_set_header(client, "If-None-Match", etag);
    }

    esp_err_t err = esp_http_client_open(client, 0);
    if (err == ESP_OK) {
        esp_http_client_fetch_headers(client);
        res->status = esp_http_client_get_status_code(client);
        if (res->status == 200) {
            size_t total = 0;
            while (total < cap) {
                int n = esp_http_client_read(client, (char *)buf + total, (int)(cap - total));
                if (n < 0) {
                    err = ESP_FAIL;
                    break;
                }
                if (n == 0) {
                    break;
                }
                total += (size_t)n;
            }
            if (err == ESP_OK && total == cap) {
                char extra;
                if (esp_http_client_read(client, &extra, 1) > 0) {
                    total = cap + 1;
                }
            }
            res->len = total;
        }
    } else {
        ESP_LOGE(TAG, "http open failed: %s", esp_err_to_name(err));
    }
    esp_http_client_close(client);
    esp_http_client_cleanup(client);
    return err;
}
