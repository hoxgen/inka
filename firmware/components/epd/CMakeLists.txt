idf_component_register(
    SRCS "epd.c"
    INCLUDE_DIRS "include"
    REQUIRES esp_driver_spi esp_driver_gpio esp_timer fb
)
