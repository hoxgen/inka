idf_component_register(
    SRCS "net.c"
    INCLUDE_DIRS "include"
    REQUIRES esp_wifi esp_netif esp_event esp_http_client mbedtls cycle
)
