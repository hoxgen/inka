#pragma once
#include <stdint.h>
#include "esp_err.h"

#ifdef __cplusplus
extern "C" {
#endif

esp_err_t epd_init(void);
esp_err_t epd_show(const uint8_t *buf);
void      epd_sleep(void);

#ifdef __cplusplus
}
#endif
