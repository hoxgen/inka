#pragma once
#include <limits.h>
#include <stddef.h>

#ifdef __cplusplus
extern "C" {
#endif

#define CYCLE_MIN_SLEEP_S        30  // ladicí režim serveru
#define CYCLE_MIN_RETRY_S        60
#define CYCLE_MAX_SLEEP_S        604800
#define CYCLE_DEFAULT_INTERVAL_S 3600

#define CYCLE_NO_TEMP INT_MIN

// Hlášení stavu do query; záporné hodnoty (a CYCLE_NO_TEMP) se vynechají.
typedef struct {
    int battery_mv;
    int battery_pct;
    int charging;
    int temp_c10;  // desetiny °C
    int usb;       // napájení z USB: 1/0, -1 neznámé
} cycle_report_t;

typedef enum {
    CYCLE_MODE_UNKNOWN = -1,
    CYCLE_MODE_LIGHT   = 0,
    CYCLE_MODE_DEEP    = 1,
} cycle_mode_t;

int          cycle_retry_delay_s(int failures, int interval_s);
int          cycle_parse_sleep_s(const char *value, int fallback);
cycle_mode_t cycle_parse_mode(const char *value);
// "landscape;rot180" → portrait=0, rot180=1. Vrací 0, při chybě -1 a výstupy nemění.
int          cycle_parse_view(const char *value, int *portrait, int *rot180);
int          cycle_build_query(char *out, size_t size, const cycle_report_t *r, const char *fw, const char *wake);

#ifdef __cplusplus
}
#endif
