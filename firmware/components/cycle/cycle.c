#include <ctype.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include "cycle.h"

static int clamp(long v, long lo, long hi) {
    return (int)(v < lo ? lo : (v > hi ? hi : v));
}

int cycle_retry_delay_s(int failures, int interval_s) {
    static const int steps[] = {60, 300, 900};
    int delay = failures >= 1 && failures <= 3 ? steps[failures - 1] : interval_s;
    if (delay > interval_s) {
        delay = interval_s;
    }
    return delay < CYCLE_MIN_RETRY_S ? CYCLE_MIN_RETRY_S : delay;
}

int cycle_parse_sleep_s(const char *value, int fallback) {
    if (value == NULL || *value == '\0') {
        return fallback;
    }
    char *end = NULL;
    long v = strtol(value, &end, 10);
    if (end == value || *end != '\0') {
        return fallback;
    }
    return clamp(v, CYCLE_MIN_SLEEP_S, CYCLE_MAX_SLEEP_S);
}

cycle_mode_t cycle_parse_mode(const char *value) {
    if (value == NULL) {
        return CYCLE_MODE_UNKNOWN;
    }
    if (strcmp(value, "light") == 0) {
        return CYCLE_MODE_LIGHT;
    }
    if (strcmp(value, "deep") == 0) {
        return CYCLE_MODE_DEEP;
    }
    return CYCLE_MODE_UNKNOWN;
}

// Procentové kódování; vrací potřebnou délku bez NUL (i když se nevejde).
static size_t encode(char *out, size_t size, const char *s) {
    static const char hex[] = "0123456789ABCDEF";
    size_t n = 0;
    for (; *s; s++) {
        unsigned char c = (unsigned char)*s;
        if (isalnum(c) || c == '.' || c == '_' || c == '~' || c == '-') {
            if (n + 1 < size) out[n] = (char)c;
            n += 1;
        } else {
            if (n + 3 < size) {
                out[n] = '%';
                out[n + 1] = hex[c >> 4];
                out[n + 2] = hex[c & 0x0F];
            }
            n += 3;
        }
    }
    if (n < size) out[n] = '\0';
    return n;
}

int cycle_build_query(char *out, size_t size, const cycle_report_t *r, const char *fw, const char *wake) {
    char fw_enc[96];
    char wake_enc[32];
    if (encode(fw_enc, sizeof(fw_enc), fw) >= sizeof(fw_enc) ||
        encode(wake_enc, sizeof(wake_enc), wake) >= sizeof(wake_enc)) {
        return -1;
    }
    char parts[96] = "";
    size_t used = 0;
    if (r->battery_mv >= 0) {
        used += snprintf(parts + used, sizeof(parts) - used, "battery_mv=%d&", r->battery_mv);
    }
    if (r->battery_pct >= 0) {
        used += snprintf(parts + used, sizeof(parts) - used, "battery_pct=%d&", r->battery_pct);
    }
    if (r->charging >= 0) {
        used += snprintf(parts + used, sizeof(parts) - used, "charging=%d&", r->charging ? 1 : 0);
    }
    if (r->temp_c10 != CYCLE_NO_TEMP) {
        int a = r->temp_c10 < 0 ? -r->temp_c10 : r->temp_c10;
        used += snprintf(parts + used, sizeof(parts) - used, "temp_c=%s%d.%d&", r->temp_c10 < 0 ? "-" : "", a / 10, a % 10);
    }
    if (r->usb >= 0 && used < sizeof(parts)) {
        used += snprintf(parts + used, sizeof(parts) - used, "usb=%d&", r->usb ? 1 : 0);
    }
    int n = snprintf(out, size, "?%sfw=%s&wake=%s", parts, fw_enc, wake_enc);
    return (n < 0 || (size_t)n >= size) ? -1 : n;
}

int cycle_parse_view(const char *value, int *portrait, int *rot180) {
    if (value == NULL) {
        return -1;
    }
    int p, r;
    if (strncmp(value, "landscape;", 10) == 0) {
        p = 0;
    } else if (strncmp(value, "portrait;", 9) == 0) {
        p = 1;
    } else {
        return -1;
    }
    const char *rot = strchr(value, ';') + 1;
    if (strcmp(rot, "rot180") == 0) {
        r = 1;
    } else if (strcmp(rot, "rot0") == 0) {
        r = 0;
    } else {
        return -1;
    }
    *portrait = p;
    *rot180 = r;
    return 0;
}
