#pragma once
#include "cycle.h"
#include "esp_err.h"

#ifdef __cplusplus
extern "C" {
#endif

typedef struct {
    char         ssid[33];
    char         pass[65];
    char         server_url[128];
    char         token[65];
    cycle_mode_t sleep_mode;
} inka_config_t;

esp_err_t config_load(inka_config_t *c);
esp_err_t config_set_sleep_mode(cycle_mode_t mode);

#ifdef __cplusplus
}
#endif
