# Agent Continuation Guide

This repository is a Pynab fork/branch used to turn a TagTagTag Nabaztag into a
Home Assistant voice satellite. The current working branch is
`nabaztag-wyoming-baseline`.

Use this file as the handoff point for future agents. The operational setup
should be recoverable from this file plus `wyoming/README.md`.

## Current Architecture

The Nabaztag keeps Pynab for hardware control: ears, LEDs, audio playback, RFID,
web UI, and the `nabd` TCP protocol on `127.0.0.1:10543`.

Wake word recognition does not run on the original Pi Zero. Home Assistant runs
the wake word, STT, Assist, and TTS pipeline. The Nabaztag streams microphone
audio to Home Assistant through upstream Wyoming Satellite.

Runtime components on the Nabaztag:

- Pynab checkout: `/opt/pynab`
- Pynab venv: `/opt/pynab/venv`
- Upstream Wyoming Satellite checkout: `/opt/wyoming-satellite`
- Wyoming Satellite service: `wyoming-satellite.service`
- Home Assistant bridge service: `habridge.service`
- Bridge HTTP API: `http://nabaztag.local:10544`
- Wyoming endpoint for Home Assistant: `tcp://nabaztag.local:10500`
- Local `nabd` endpoint: `127.0.0.1:10543`

Home Assistant runs in an Unraid Docker container. The container id seen during
setup was `bf8dcc8415e0`, but do not assume it is permanent. The Home Assistant
package path inside the container is:

```text
/config/packages/nabaztag.yaml
```

The package source in this repo is:

```text
habridge/home-assistant-package.yaml
```

## Hardware And OS

The stable hardware target is the original Pi Zero inside the Nabaztag with the
TagTagTag board. The OS used for the working setup is Raspberry Pi OS Legacy
32-bit Lite with Python 3.9.

Installed and working hardware drivers:

- WM8960 sound driver from `pguyot/wm8960`, branch `tagtagtag-sound`
- TagTagTag ears driver from `pguyot/tagtagtag-ears`
- CR14 RFID driver from `pguyot/cr14`

The explicit ALSA commands used by Wyoming Satellite are:

```sh
arecord -D plughw:CARD=tagtagtagsound -r 16000 -c 1 -f S16_LE -t raw
aplay -D plughw:CARD=tagtagtagsound -r 22050 -c 1 -f S16_LE -t raw
```

The speaker rate was corrected back to 22050 Hz after sounding too low at
16000 Hz.

The TagTagTag board microphones work, but the case muffles them because the
microphones are not aligned with the original microphone hole. There is also a
high-frequency noise component. Treat microphone hardware/acoustics as an open
future project.

## Secrets And Local Files

Do not commit real Home Assistant tokens, URLs, or user-specific network
settings.

`habridge/habridge.conf` is tracked as a template, but the device copy may have
local values:

```sh
HABRIDGE_HA_URL=http://<home-assistant-lan-ip>:8123
HABRIDGE_HA_TOKEN=<long-lived-access-token>
```

If pulling on the Nabaztag conflicts because `habridge.conf` was edited locally,
preserve the local file like this:

```sh
cd /opt/pynab
cp habridge/habridge.conf /tmp/habridge.conf.local
git restore habridge/habridge.conf
git pull --ff-only
cp /tmp/habridge.conf.local habridge/habridge.conf
sudo systemctl restart habridge.service
```

There is an untracked `GEMINI.md` in this local workspace. It was not created by
this agent; leave it alone unless the user explicitly asks.

## Service Profile

The intended voice-focused services are:

```text
nabboot.service
nabd.service
nabweb-boot.service
nabweb.service
nabwebhook.service
habridge.service
wyoming-satellite.service
```

The user currently also keeps these local services enabled because they are cute
or useful, but quiet mode can stop them:

```text
nabclockd.service
nabsurprised.service
nabtaichid.service
```

Usually disabled because they are not needed or too heavy on the Pi Zero:

```text
nab8balld.service
nabairqualityd.service
nabbookd.service
nabiftttd.service
nabmastodond.service
nabradio.service
nabweatherd.service
wyoming-bridge.service
```

`nabclockd` has a `Stay awake` setting in the web UI. Enable it if `nabclockd`
is running. Scheduled sleep made Wyoming/LED feedback unreliable after the
rabbit went to sleep.

Quiet mode is designed for living-room/media-center use. It leaves voice and
RFID available, turns off the fuchsia bottom status pulse, and stops local
clock/surprise/taichi services. It is exposed in the web UI and through the
bridge:

```sh
curl -X POST http://127.0.0.1:10544/quiet/on
curl -X POST http://127.0.0.1:10544/quiet/off
```

Override quiet-mode service lists with:

- `HABRIDGE_QUIET_SERVICES` in `habridge/habridge.conf`
- `NABWEB_QUIET_SERVICES` for the web UI

## Bridge API

`habridge.service` exposes HTTP on port `10544` and translates requests to
`nabd` packets.

Endpoints:

```text
GET  /health
POST /leds/info
POST /leds/clear
POST /leds/reset
POST /ears
POST /sleep
POST /wakeup
POST /quiet
POST /quiet/on
POST /quiet/off
POST /audio/url
POST /tts/ha
POST /weather/say
POST /packet
```

Useful distinctions:

- `/leds/clear` clears one named idle `info` animation.
- `/leds/reset` sends a direct all-LEDs-off choreography for stuck LEDs.
- `/tts/ha` asks Home Assistant TTS for an MP3 and asks `nabd` to play it.
- `/weather/say` prepares the weather sentence inside the bridge, asks Home
  Assistant TTS for speech, and sends a combined audio/LED/ear choreography.
- `/packet` sends a raw `nabd` packet and is useful only for experiments.

The bridge needs the native MP3 decoder for TTS playback:

```sh
sudo apt-get install -y libmpg123-0 mpg123
```

## Home Assistant Package

The package currently defines rest commands and scripts for:

```text
script.nabaztag_move_ears
script.nabaztag_led_effect
script.nabaztag_clear_led_effect
script.nabaztag_reset_leds
script.nabaztag_sleep
script.nabaztag_wakeup
script.nabaztag_quiet_on
script.nabaztag_quiet_off
script.nabaztag_show_weather
```

`script.nabaztag_show_weather` does not need the Nabaztag to be a
`media_player`. It sends weather values to `/weather/say`; the bridge then
generates the German sentence and plays the MP3 returned by Home Assistant TTS.
Temperature is rounded for speech. Wind speed is included when the Home
Assistant weather entity exposes `wind_speed`.

When the package changes, copy it into Home Assistant and restart/reload Home
Assistant. The setup used during development was:

From Windows:

```powershell
scp C:\Code\pynab\habridge\home-assistant-package.yaml root@tower.local:/root/home-assistant-package.yaml
```

From the Unraid server:

```sh
docker cp /root/home-assistant-package.yaml bf8dcc8415e0:/config/packages/nabaztag.yaml
docker restart bf8dcc8415e0
```

If Home Assistant packages are not enabled, `configuration.yaml` needs:

```yaml
homeassistant:
  packages: !include_dir_named packages
```

Be careful editing YAML from a shell: unquoted `!include_dir_named` can trigger
bash history expansion.

## RFID

`nabwebhook.service` is enabled because RFID tags are useful for Home Assistant
automations. Pynab stores a webhook URL for a tag. On scan, `nabwebhook` calls
that URL with HTTP GET.

In Home Assistant, create a webhook trigger with:

```text
Allowed methods: GET
Local only: enabled
```

Then store this on the RFID tag through the Pynab web UI:

```text
http://<home-assistant-ip>:8123/api/webhook/<webhook-id>
```

Future improvement: build a single Home Assistant webhook endpoint that receives
the RFID UID and dispatches in HA, instead of storing a different HA webhook URL
on every tag.

## Applying Repo Updates On The Device

General update command:

```sh
cd /opt/pynab
git pull --ff-only
venv/bin/python manage.py migrate nabd nabclockd
sudo systemctl restart nabd.service nabweb.service habridge.service nabclockd.service
```

Restart Wyoming separately if the satellite code or service file changed:

```sh
sudo systemctl restart wyoming-satellite.service
```

After changing `habridge/habridge.service`:

```sh
sudo cp habridge/habridge.service /lib/systemd/system/habridge.service
sudo systemctl daemon-reload
sudo systemctl restart habridge.service
```

After changing `habridge/home-assistant-package.yaml`, update Home Assistant as
described above.

## Testing And Diagnostics

Local repo test that has passed on this workstation:

```sh
python -m unittest nabd.tests.leds_test -q
```

Bridge health on the device:

```sh
curl http://127.0.0.1:10544/health
```

Wyoming logs:

```sh
sudo journalctl -u wyoming-satellite.service -f
```

Stop Wyoming for a clean audio recording test:

```sh
sudo systemctl stop wyoming-satellite.service
arecord -D plughw:CARD=tagtagtagsound -r 16000 -c 1 -f S16_LE -d 10 /tmp/mic-test.wav
sudo systemctl start wyoming-satellite.service
```

Audio overruns and `BrokenPipeError` appeared after long runtime once. A clean
`arecord` test suggested the mic command could still record, and reconnects to
Home Assistant were logged. Treat this as unresolved reliability work; check HA
load/logs and network before changing audio code.

## Code Areas

Key files for this branch:

```text
habridge/server.py
habridge/home-assistant-package.yaml
habridge/habridge.service
habridge/habridge.conf
nabd/leds.py
nabd/models.py
nabd/migrations/0003_config_quiet_mode.py
nabclockd/models.py
nabclockd/migrations/0005_config_stay_awake.py
nabweb/views.py
nabweb/templates/nabweb/index.html
wyoming/README.md
```

## Future Work

High-value next steps:

- Diagnose the intermittent Wyoming ping timeout/overrun after long uptime.
- Improve microphone hardware/acoustics or find a better tiny mic option.
- Add a cleaner RFID-to-Home-Assistant dispatch model.
- Consider HA-driven weather forecast/night summary if the HA weather entity
  exposes forecast data.
- Decide whether quiet mode should restore previous service states instead of
  always starting the configured list on quiet-off.
- Consider a proper Home Assistant custom integration only after the bridge API
  has settled. The current package/bridge approach is simpler and works.

## Working Style

Use existing Pynab patterns and keep changes small. This repo may have dirty
local files, especially device-specific bridge config. Do not revert or overwrite
user changes unless explicitly asked.

Use `apply_patch` for manual edits. Avoid committing secrets. Keep docs updated
whenever changing device setup, Home Assistant package behavior, or service
profile assumptions.
