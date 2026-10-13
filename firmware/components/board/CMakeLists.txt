idf_component_register(
    SRCS "board.cpp" "xpowers/XPowersLibInterface.cpp"
    INCLUDE_DIRS "include"
    PRIV_INCLUDE_DIRS "xpowers" "xpowers/REG"
    REQUIRES esp_driver_i2c esp_driver_gpio
)
target_compile_definitions(${COMPONENT_LIB} PRIVATE XPOWERS_CHIP_AXP2101 CONFIG_XPOWERS_ESP_IDF_NEW_API)
target_compile_options(${COMPONENT_LIB} PRIVATE -Wno-unused-variable -Wno-unused-function)
