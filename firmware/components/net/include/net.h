#pragma once
#include <stddef.h>
#include <stdint.h>
#include "cycle.h"
#include "esp_err.h"

#ifdef __cplusplus
extern "C" {
#endif

typedef struct {
    int          status;
    int          sleep_s;
    int          interval_s;
    cycle_mode_t sleep_mode;
    char         etag[48];
    int          portrait;  // -1 = hlavička chyběla
    int          rot180;
    size_t       len;
} net_frame_t;

esp_err_t net_wifi_init(void);
esp_err_t net_wifi_connect(const char *ssid, const char *pass, int timeout_ms);
void      net_wifi_disconnect(void);
esp_err_t net_fetch_frame(const char *url, const char *token, const char *etag,
                          uint8_t *buf, size_t cap, net_frame_t *res);

#ifdef __cplusplus
}
#endif
