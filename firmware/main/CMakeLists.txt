idf_component_register(
    SRCS "main.c"
    REQUIRES board epd fb framestore cycle config net esp_psram esp_app_format esp_driver_gpio
)
