# Hardware notes

Board: Waveshare ESP32-S3-PhotoPainter Rev2.0.

- Chip: ESP32-S3 (QFN56) rev. v0.2.
- Memory: 16 MB flash, 8 MB octal PSRAM.
- PMIC: AXP2101 at I²C address 0x34.

Everything below was measured on one board in October 2026.

## Panel

- The six colour indices match `enum fb_color`: black 0, white 1, yellow 2, red 3, blue 5, green 6.
- A full refresh (`epd_show`) takes **30.2 s**.
- `epd_init` finishes about 0.45 s after boot.

## Orientation

The frame stands in landscape on its stand, with the USB-C cable leaving at the bottom left as seen from the front.

- Buffer pixel `(0, 0)` is at the **bottom right** as seen from the front, so the buffer is rotated 180° (not mirrored).
- The server therefore rotates the image 180° before packing it. This is a setting (`rotate_180`), because the frame can also stand the other way up.

## Flashing

- `idf.py flash` works without pressing any buttons (automatic download mode over USB-Serial-JTAG).
- In deep sleep the USB port disappears. In the default `auto` power mode, connect USB, wake the frame with KEY or PWR and wait for `mode light` in the log. If the mode is forced to battery (deep), first switch it to mains or auto in the web UI.
- Fallback: hold BOOT while power-cycling with PWR. Not tested yet.
- macOS: if the shell profile exports `CPLUS_INCLUDE_PATH` or `SDKROOT` pointing at the macOS SDK headers, cross-compiling fails with `#error "No thread API"`. `tools/env.sh` unsets these variables.
- `tools/serial_wait.py` needs pyserial. Outside `tools/env.sh`, run it as `uv run --with pyserial python tools/serial_wait.py …`.

## Fetch cycle

These measurements were taken with the server on a Mac on the local network and the frame on the same Wi-Fi.

| Situation | Result |
|---|---|
| Boot (`wake=boot`) | Wi-Fi up 2.1 s after boot. Download of 192,000 B plus `epd init` take ~1.3 s, then a 30.2 s refresh. |
| Timer wake | Next photo after the interval from `X-Inka-Sleep-Seconds`. |
| KEY button | Immediate wake with `wake=button`. The server advances to the next photo. |
| Unchanged photo | `304 Not Modified`. The whole cycle takes 1.4 s without a redraw. |
| Server unreachable | `ESP_ERR_HTTP_CONNECT`. The frame keeps the image and retries after 60 s, 300 s and 900 s, then at the normal interval. |
| Production over HTTPS (Cloudflare tunnel) | Cycle takes 3.9 s: Wi-Fi 1.7 s, HTTPS 1.6 s. |

## Power button and shutdown

- PMIC hard power-off is set explicitly to a ~10 s hold (`XPOWERS_POWEROFF_10S`). It works on USB power too.
- PWR can be read on GPIO 5 (pressed = 1).
- After a 2 s hold the firmware shuts down cleanly:
  1. The red LED blinks three times and stays on.
  2. An OFF badge is drawn into the last image, in the bottom right corner of the view (`X-Inka-View`).
  3. The panel redraws (30 s) and the PMIC powers off (`shutdown()`).
- A short press while the frame is off powers it on: it boots, downloads and redraws.
- LEDs:
  - red = **PWR** (shutting down; steady red without a redraw means the frame is not provisioned),
  - green = **ACT** (downloading and redrawing).

## Deep sleep and battery

- The server picks the sleep mode with the `X-Inka-Sleep-Mode` header.
  - The firmware reports `usb=1|0` from the AXP2101 VBUS state.
  - In `auto` mode (the default) the server answers `light` on USB and `deep` on battery.
- Deep sleep wakes on a timer, KEY or PWR. The ETag survives in RTC memory, so an unchanged photo costs one `304` and 3.8 s awake.
- Before deep sleep, the current image is written to a dedicated `frame` flash partition (type `0x40/0x00`, ~1.1 s). The write happens only when the image changed. The PWR shutdown uses the stored image to draw the OFF badge.
- The firmware reports `battery_pct`, `charging` and `temp_c` (SHTC3 sensor) with every request.
- During a cycle in battery mode the firmware ignores KEY events. Otherwise the button bounce on release starts a second cycle and skips a photo.
- SHTC3 timing: after the wake-up command the firmware busy-waits 500 µs (`esp_rom_delay_us`), because `pdMS_TO_TICKS(1)` is 0 at a 100 Hz tick rate and the sensor answered with a NACK. The wake-up takes up to 240 µs. The measurement wait is 30 ms: 3 ticks guarantee at least 20 ms, and a measurement takes up to 12.1 ms.
- Deep sleep current has not been measured yet.

## Palette calibration

The panel's real colours differ a lot from nominal sRGB. The server dithers into a measured palette, which is the default (`DEFAULT_PALETTE` in `server/src/inka_server/settings.py`). Another panel may differ; the palette can be overridden in `DATA_DIR/settings.json`.

How the palette was measured:

1. The panel showed six stripes, one per palette colour.
2. A MacBook camera took the photos.
3. A Pantone strip next to the panel provided white balance: in linear RGB, the paper was set to 245.
4. A check against the Pantone C patches gave these errors: cyan Δ2, black Δ9, magenta Δ13, yellow Δ24 (the camera undersaturates yellow).

| Colour | Nominal guess | Measured |
|---|---|---|
| black | 30, 30, 40 | 37, 33, 47 |
| white | 190, 200, 200 | 175, 185, 188 |
| yellow | 200, 190, 40 | 196, 170, 53 |
| red | 130, 15, 20 | 128, 17, 23 |
| blue | 20, 80, 170 | 9, 69, 133 |
| green | 30, 85, 60 | 64, 89, 74 |

Findings:

- **The panel white is dark and cool**, only about 180/255. Everything above ~170 merges with the white.
- **Mid-greys drift green.** A dithered grey ramp shows a* of −3 to −4.5 in the midtones, and the black is blue-violet.
- **The panel does not mix colours linearly.** The measured palette predicts neutral mixes, but isolated pixels do not average out. Any correction must therefore be empirical.
- **CIELAB doesn't help.** Choosing the nearest colour in CIELAB instead of RGB does not change the appearance of a mix in theory, so the experiment was dropped.

## Warmth and tint

Two corrections are applied in linear light before dithering:

- **warmth** is a blue↔yellow gain,
- **tint** is a green↔magenta gain.

Grey ramp on the panel, dithered with JJN. Each cell shows L* a* b* as measured by the camera, balanced on the paper:

| Setting | 32 | 64 | 96 | 128 | 160 | Mean chroma 64–160 |
|---|---|---|---|---|---|---|
| none | 13 +6.6 −11.1 | 34 −3.8 +3.7 | 44 −4.5 +4.4 | 49 −2.6 +2.3 | 70 −2.2 −1.2 | 4.4 |
| tint 0.4 | 13 +5.9 −11.5 | 33 −2.3 +2.0 | 42 −0.5 −0.4 | 46 +1.1 −3.8 | 69 +0.8 −4.4 | 2.9 |
| **warmth 0.3 + tint 0.4** | 13 +7.3 −10.9 | 34 −1.4 +3.2 | 43 −1.3 +3.3 | 47 −0.4 +0.0 | 69 +1.5 −0.9 | **2.3** |
| warmth 0.4 + tint 0.5 | 13 +6.4 −11.7 | 33 −1.0 +2.4 | 42 −1.2 +2.5 | 46 +0.9 −0.9 | 69 +2.8 −2.1 | 2.5 |

The camera is a guide, but looking at the panel decides. The current settings were picked by eye on the live panel:

- dithering: serpentine Floyd–Steinberg, diffusion 1.0,
- saturation 0.9,
- warmth 0.5, tint 0.4,
- the measured palette.

`tools/panel_metric.py` compares a camera shot of the panel with the original photo in CIELAB. It is unreliable for dark photos, because window reflections on the glass dominate the shadows.
