#include <assert.h>
#include <stdio.h>
#include <string.h>
#include "cycle.h"

static void test_retry_delay(void) {
    assert(cycle_retry_delay_s(1, 3600) == 60);
    assert(cycle_retry_delay_s(2, 3600) == 300);
    assert(cycle_retry_delay_s(3, 3600) == 900);
    assert(cycle_retry_delay_s(4, 3600) == 3600);
    assert(cycle_retry_delay_s(50, 3600) == 3600);
    assert(cycle_retry_delay_s(3, 600) == 600);
    assert(cycle_retry_delay_s(1, 10) == 60);
}

static void test_parse_sleep(void) {
    assert(cycle_parse_sleep_s("230", -1) == 230);
    assert(cycle_parse_sleep_s("5", -1) == 30);
    assert(cycle_parse_sleep_s("30", -1) == 30);
    assert(cycle_parse_sleep_s("99999999", -1) == 604800);
    assert(cycle_parse_sleep_s(NULL, -1) == -1);
    assert(cycle_parse_sleep_s("", 77) == 77);
    assert(cycle_parse_sleep_s("12abc", 77) == 77);
    assert(cycle_parse_sleep_s("-5", 77) == 30);
}

static void test_parse_mode(void) {
    assert(cycle_parse_mode("light") == CYCLE_MODE_LIGHT);
    assert(cycle_parse_mode("deep") == CYCLE_MODE_DEEP);
    assert(cycle_parse_mode("Deep") == CYCLE_MODE_UNKNOWN);
    assert(cycle_parse_mode(NULL) == CYCLE_MODE_UNKNOWN);
}

static void test_build_query(void) {
    char buf[160];
    cycle_report_t r = {3790, 54, 1, 225, 1};
    int n = cycle_build_query(buf, sizeof(buf), &r, "29fdea6-dirty", "timer");
    assert(n == (int)strlen(buf));
    assert(strcmp(buf, "?battery_mv=3790&battery_pct=54&charging=1&temp_c=22.5&usb=1&fw=29fdea6-dirty&wake=timer") == 0);
    cycle_report_t none = {-1, -1, -1, CYCLE_NO_TEMP, -1};
    cycle_build_query(buf, sizeof(buf), &none, "v1+x y", "boot");
    assert(strcmp(buf, "?fw=v1%2Bx%20y&wake=boot") == 0);
    cycle_report_t neg = {-1, -1, 0, -35, 0};
    cycle_build_query(buf, sizeof(buf), &neg, "v", "boot");
    assert(strcmp(buf, "?charging=0&temp_c=-3.5&usb=0&fw=v&wake=boot") == 0);
    assert(cycle_build_query(buf, 10, &r, "abc", "timer") == -1);
}

static void test_parse_view(void) {
    int portrait = -1, rot180 = -1;
    assert(cycle_parse_view("landscape;rot180", &portrait, &rot180) == 0);
    assert(portrait == 0 && rot180 == 1);
    assert(cycle_parse_view("portrait;rot0", &portrait, &rot180) == 0);
    assert(portrait == 1 && rot180 == 0);
    portrait = 7;
    assert(cycle_parse_view("diagonal", &portrait, &rot180) == -1);
    assert(portrait == 7);  // při chybě beze změny
    assert(cycle_parse_view(NULL, &portrait, &rot180) == -1);
}

int main(void) {
    test_retry_delay();
    test_parse_sleep();
    test_parse_mode();
    test_build_query();
    test_parse_view();
    puts("cycle: all tests passed");
    return 0;
}
