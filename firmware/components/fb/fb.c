#include <string.h>
#include "fb.h"

static int in_range(int x, int y) {
    return x >= 0 && y >= 0 && x < FB_WIDTH && y < FB_HEIGHT;
}

void fb_fill(uint8_t *buf, uint8_t color) {
    memset(buf, (uint8_t)((color << 4) | (color & 0x0F)), FB_LEN);
}

void fb_set_pixel(uint8_t *buf, int x, int y, uint8_t color) {
    if (!in_range(x, y)) {
        return;
    }
    uint8_t *p = &buf[y * (FB_WIDTH / 2) + x / 2];
    if (x & 1) {
        *p = (uint8_t)((*p & 0xF0) | (color & 0x0F));
    } else {
        *p = (uint8_t)((*p & 0x0F) | (color << 4));
    }
}

uint8_t fb_get_pixel(const uint8_t *buf, int x, int y) {
    if (!in_range(x, y)) {
        return 0xFF;
    }
    uint8_t b = buf[y * (FB_WIDTH / 2) + x / 2];
    return (x & 1) ? (b & 0x0F) : (b >> 4);
}

void fb_test_stripes(uint8_t *buf) {
    static const uint8_t order[6] = {FB_BLACK, FB_WHITE, FB_YELLOW, FB_RED, FB_BLUE, FB_GREEN};
    static const int ends[6] = {134, 267, 400, 533, 666, 800};
    for (int y = 0; y < FB_HEIGHT; y++) {
        int stripe = 0;
        for (int x = 0; x < FB_WIDTH; x++) {
            while (x >= ends[stripe]) {
                stripe++;
            }
            fb_set_pixel(buf, x, y, order[stripe]);
        }
    }
}

void fb_view_to_native(int vx, int vy, int portrait, int rot180, int *nx, int *ny) {
    int x = vx, y = vy;
    if (portrait) {  // pohled 480×800 → nativní 800×480
        x = vy;
        y = (FB_HEIGHT - 1) - vx;
    }
    if (rot180) {
        x = (FB_WIDTH - 1) - x;
        y = (FB_HEIGHT - 1) - y;
    }
    *nx = x;
    *ny = y;
}

static void view_pixel(uint8_t *buf, int portrait, int rot180, int vx, int vy, uint8_t color) {
    int x, y;
    fb_view_to_native(vx, vy, portrait, rot180, &x, &y);
    fb_set_pixel(buf, x, y, color);
}

// 5×7 písmo, jen znaky potřebné pro štítek.
static const uint8_t GLYPH_O[7] = {0x0E, 0x11, 0x11, 0x11, 0x11, 0x11, 0x0E};
static const uint8_t GLYPH_F[7] = {0x1F, 0x10, 0x10, 0x1E, 0x10, 0x10, 0x10};

#define BADGE_W      64
#define BADGE_H      30
#define BADGE_MARGIN 14
#define BADGE_SCALE  3

void fb_draw_off_badge(uint8_t *buf, int portrait, int rot180) {
    const int view_w = portrait ? FB_HEIGHT : FB_WIDTH;
    const int view_h = portrait ? FB_WIDTH : FB_HEIGHT;
    const int x0 = view_w - BADGE_MARGIN - BADGE_W;
    const int y0 = view_h - BADGE_MARGIN - BADGE_H;
    for (int y = 0; y < BADGE_H; y++) {
        for (int x = 0; x < BADGE_W; x++) {
            int cx = x < 3 ? 3 - x : (x >= BADGE_W - 3 ? x - (BADGE_W - 4) : 0);
            int cy = y < 3 ? 3 - y : (y >= BADGE_H - 3 ? y - (BADGE_H - 4) : 0);
            if (cx * cx + cy * cy > 9) {
                continue;  // zaoblené rohy
            }
            view_pixel(buf, portrait, rot180, x0 + x, y0 + y, FB_BLACK);
        }
    }
    const uint8_t *text[3] = {GLYPH_O, GLYPH_F, GLYPH_F};
    const int glyph_w = 5 * BADGE_SCALE, gap = BADGE_SCALE;
    const int text_w = 3 * glyph_w + 2 * gap;
    const int tx = x0 + (BADGE_W - text_w) / 2;
    const int ty = y0 + (BADGE_H - 7 * BADGE_SCALE) / 2;
    for (int g = 0; g < 3; g++) {
        for (int row = 0; row < 7; row++) {
            for (int col = 0; col < 5; col++) {
                if (!(text[g][row] & (0x10 >> col))) {
                    continue;
                }
                for (int sy = 0; sy < BADGE_SCALE; sy++) {
                    for (int sx = 0; sx < BADGE_SCALE; sx++) {
                        view_pixel(buf, portrait, rot180,
                                   tx + g * (glyph_w + gap) + col * BADGE_SCALE + sx,
                                   ty + row * BADGE_SCALE + sy, FB_WHITE);
                    }
                }
            }
        }
    }
}
