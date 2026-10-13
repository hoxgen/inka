#pragma once
#include <stdbool.h>
#include "esp_err.h"

#ifdef __cplusplus
extern "C" {
#endif

typedef enum { BOARD_LED_RED, BOARD_LED_GREEN } board_led_t;

esp_err_t board_init(void);
int       board_battery_mv(void);
bool      board_is_charging(void);
void      board_led(board_led_t led, bool on);
bool      board_pwr_pressed(void);  // tlačítko PWR (GPIO 5, stisk = log. 1)
void      board_power_off(void);    // vypne napájení přes PMIC; z napájení USB i baterie
bool      board_usb_powered(void);       // napětí z USB (VBUS) přítomné
int       board_battery_percent(void);   // 0–100, -1 bez PMIC nebo baterie
int       board_temperature_c10(void);   // SHTC3, desetiny °C; INT_MIN při chybě
void      board_prepare_deep_sleep(void); // zhasnout LED a podržet piny během spánku

#ifdef __cplusplus
}
#endif
