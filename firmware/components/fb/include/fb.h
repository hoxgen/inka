#pragma once
#include <stdint.h>

#ifdef __cplusplus
extern "C" {
#endif

#define FB_WIDTH  800
#define FB_HEIGHT 480
#define FB_LEN    (FB_WIDTH * FB_HEIGHT / 2)

enum fb_color {
    FB_BLACK  = 0,
    FB_WHITE  = 1,
    FB_YELLOW = 2,
    FB_RED    = 3,
    FB_BLUE   = 5,
    FB_GREEN  = 6,
};

void    fb_fill(uint8_t *buf, uint8_t color);
void    fb_set_pixel(uint8_t *buf, int x, int y, uint8_t color);
uint8_t fb_get_pixel(const uint8_t *buf, int x, int y);
void    fb_test_stripes(uint8_t *buf);

// Souřadnice v orientaci pohledu (jak visí na zdi) → nativní buffer panelu.
// Shodné se serverem: portrait = rot90(k=1), rot180 = rot90(k=2).
void    fb_view_to_native(int vx, int vy, int portrait, int rot180, int *nx, int *ny);
// Malý štítek „OFF“ v pravém dolním rohu pohledu.
void    fb_draw_off_badge(uint8_t *buf, int portrait, int rot180);

#ifdef __cplusplus
}
#endif
