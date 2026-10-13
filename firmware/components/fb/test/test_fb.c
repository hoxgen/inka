#include <assert.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>
#include "fb.h"

static uint8_t buf[FB_LEN];

static void test_len(void) {
    assert(FB_LEN == FB_WIDTH * FB_HEIGHT / 2);
    assert(FB_LEN == 192000);
}

static void test_fill_packs_two_pixels_per_byte(void) {
    fb_fill(buf, FB_RED);
    assert(buf[0] == 0x33);
    assert(buf[FB_LEN - 1] == 0x33);
}

static void test_even_pixel_is_high_nibble(void) {
    fb_fill(buf, FB_WHITE);
    fb_set_pixel(buf, 0, 0, FB_BLACK);
    assert(buf[0] == 0x01);
    fb_set_pixel(buf, 1, 0, FB_GREEN);
    assert(buf[0] == 0x06);
}

static void test_row_stride_is_400_bytes(void) {
    fb_fill(buf, FB_WHITE);
    fb_set_pixel(buf, 2, 1, FB_BLUE);
    assert(buf[400 + 1] == 0x51);
    assert(fb_get_pixel(buf, 2, 1) == FB_BLUE);
    assert(fb_get_pixel(buf, 3, 1) == FB_WHITE);
}

static void test_last_pixel(void) {
    fb_fill(buf, FB_WHITE);
    fb_set_pixel(buf, 799, 479, FB_YELLOW);
    assert(buf[FB_LEN - 1] == 0x12);
}

static void test_set_pixel_out_of_range_is_ignored(void) {
    uint8_t copy[FB_LEN];
    fb_fill(buf, FB_WHITE);
    memcpy(copy, buf, FB_LEN);
    fb_set_pixel(buf, 800, 0, FB_BLACK);
    fb_set_pixel(buf, 0, 480, FB_BLACK);
    fb_set_pixel(buf, -1, 0, FB_BLACK);
    fb_set_pixel(buf, 0, -1, FB_BLACK);
    assert(memcmp(copy, buf, FB_LEN) == 0);
    assert(fb_get_pixel(buf, 800, 0) == 0xFF);
}

static void test_stripes(void) {
    const uint8_t order[6] = {FB_BLACK, FB_WHITE, FB_YELLOW, FB_RED, FB_BLUE, FB_GREEN};
    const int starts[6] = {0, 134, 267, 400, 533, 666};
    fb_test_stripes(buf);
    for (int i = 0; i < 6; i++) {
        assert(fb_get_pixel(buf, starts[i], 0) == order[i]);
        assert(fb_get_pixel(buf, starts[i], 479) == order[i]);
    }
    assert(fb_get_pixel(buf, 133, 240) == FB_BLACK);
    assert(fb_get_pixel(buf, 799, 240) == FB_GREEN);
    for (int i = 0; i < FB_LEN; i++) {
        assert((buf[i] >> 4) != 4 && (buf[i] & 0x0F) != 4);
    }
}


static int count_color(const uint8_t *b, int x0, int y0, int x1, int y1, uint8_t c) {
    int n = 0;
    for (int y = y0; y < y1; y++)
        for (int x = x0; x < x1; x++)
            n += fb_get_pixel(b, x, y) == c;
    return n;
}

static void test_view_to_native(void) {
    int x, y;
    fb_view_to_native(0, 0, 0, 0, &x, &y);
    assert(x == 0 && y == 0);
    fb_view_to_native(0, 0, 0, 1, &x, &y);  // na šířku, otočeno o 180°
    assert(x == 799 && y == 479);
    fb_view_to_native(0, 0, 1, 0, &x, &y);  // na výšku: levý horní roh → levý dolní (jako server rot90 k=1)
    assert(x == 0 && y == 479);
    fb_view_to_native(479, 799, 1, 0, &x, &y);
    assert(x == 799 && y == 0);
}

static void test_off_badge_bottom_right_of_view(void) {
    fb_fill(buf, FB_WHITE);
    fb_draw_off_badge(buf, 0, 0);
    // pravý dolní roh pohledu: černý štítek s bílým textem
    assert(count_color(buf, 700, 420, 800, 480, FB_BLACK) > 600);
    assert(count_color(buf, 700, 420, 800, 480, FB_WHITE) > 1500);
    assert(count_color(buf, 0, 0, 600, 400, FB_BLACK) == 0);
    for (int i = 0; i < FB_LEN; i++) {
        assert((buf[i] >> 4) != 4 && (buf[i] & 0x0F) != 4);
    }
}

static void test_off_badge_rotated(void) {
    fb_fill(buf, FB_WHITE);
    fb_draw_off_badge(buf, 0, 1);  // otočeno o 180° → v nativním bufferu vlevo nahoře
    assert(count_color(buf, 0, 0, 100, 60, FB_BLACK) > 600);
    assert(count_color(buf, 200, 80, 800, 480, FB_BLACK) == 0);
}

static void test_off_badge_portrait(void) {
    fb_fill(buf, FB_WHITE);
    fb_draw_off_badge(buf, 1, 0);  // pravý dolní roh pohledu na výšku → nativně vpravo dole? (480-1-vx, vy)
    int x, y;
    fb_view_to_native(479 - 20, 799 - 20, 1, 0, &x, &y);
    assert(fb_get_pixel(buf, x, y) == FB_BLACK);
}

int main(void) {
    test_len();
    test_fill_packs_two_pixels_per_byte();
    test_even_pixel_is_high_nibble();
    test_row_stride_is_400_bytes();
    test_last_pixel();
    test_set_pixel_out_of_range_is_ignored();
    test_stripes();
    test_view_to_native();
    test_off_badge_bottom_right_of_view();
    test_off_badge_rotated();
    test_off_badge_portrait();
    puts("fb: all tests passed");
    return 0;
}
