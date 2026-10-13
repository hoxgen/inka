#pragma once
#include <stdint.h>
#include "esp_err.h"

#ifdef __cplusplus
extern "C" {
#endif

// Poslední zobrazený obraz ve flash (oddíl „frame“), aby šel dokreslit štítek OFF i po hlubokém spánku.
esp_err_t framestore_save(const uint8_t *buf, int portrait, int rot180);
// ESP_ERR_NOT_FOUND, když oddíl chybí nebo data neprojdou kontrolou; orientace se vrací spolu s obrazem
esp_err_t framestore_load(uint8_t *buf, int *portrait, int *rot180);

#ifdef __cplusplus
}
#endif
