#include <string.h>
#include "esp_log.h"
#include "esp_partition.h"
#include "esp_rom_crc.h"
#include "fb.h"
#include "framestore.h"

static const char *TAG = "inka";

#define TYPE     0x40  // vlastní typ oddílu (0x40–0xFE), podtyp 0
#define DATA_OFF 4096                                  // první sektor = hlavička
#define DATA_LEN (((FB_LEN) + 4095) / 4096 * 4096)    // zarovnáno na sektory

typedef struct {
    char     magic[4];
    uint32_t crc;
    int8_t   portrait;
    int8_t   rot180;
} header_t;

static const esp_partition_t *partition(void) {
    static const esp_partition_t *p;
    if (p == NULL) {
        p = esp_partition_find_first((esp_partition_type_t)TYPE, (esp_partition_subtype_t)0, "frame");
    }
    return p;
}

esp_err_t framestore_save(const uint8_t *buf, int portrait, int rot180) {
    const esp_partition_t *p = partition();
    if (p == NULL) {
        return ESP_ERR_NOT_FOUND;
    }
    // Smazání zneplatní i hlavičku; ta se zapíše až po datech, takže přerušený zápis nic nepokazí.
    esp_err_t err = esp_partition_erase_range(p, 0, DATA_OFF + DATA_LEN);
    if (err == ESP_OK) {
        err = esp_partition_write(p, DATA_OFF, buf, FB_LEN);
    }
    if (err == ESP_OK) {
        header_t h = {{'I', 'N', 'K', 'A'}, esp_rom_crc32_le(0, buf, FB_LEN), (int8_t)portrait, (int8_t)rot180};
        err = esp_partition_write(p, 0, &h, sizeof(h));
    }
    if (err != ESP_OK) {
        ESP_LOGW(TAG, "frame store save failed: %s", esp_err_to_name(err));
    }
    return err;
}

esp_err_t framestore_load(uint8_t *buf, int *portrait, int *rot180) {
    const esp_partition_t *p = partition();
    header_t h;
    if (p == NULL || esp_partition_read(p, 0, &h, sizeof(h)) != ESP_OK || memcmp(h.magic, "INKA", 4) != 0) {
        return ESP_ERR_NOT_FOUND;
    }
    if (esp_partition_read(p, DATA_OFF, buf, FB_LEN) != ESP_OK || esp_rom_crc32_le(0, buf, FB_LEN) != h.crc) {
        return ESP_ERR_NOT_FOUND;
    }
    *portrait = h.portrait;
    *rot180 = h.rot180;
    return ESP_OK;
}
