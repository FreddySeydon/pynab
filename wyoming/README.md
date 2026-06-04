# Home Assistant Wyoming Satellite

This setup keeps Pynab on the Nabaztag and runs Wyoming Satellite from a
separate upstream checkout. Home Assistant handles wake word recognition,
speech-to-text, Assist, and text-to-speech.

The original Pi Zero should not run wake word recognition locally.

## Fresh Raspberry Pi OS notes

Use Raspberry Pi OS Legacy 32-bit Lite on an original Pi Zero. Configure a
2.4 GHz Wi-Fi network and SSH before first boot.

If the image boots as `raspberrypi.local`, rename it before installing Pynab:

```sh
sudo hostnamectl set-hostname nabaztag
sudo sed -i 's/raspberrypi/nabaztag/g' /etc/hosts
sudo reboot
```

After reboot, connect with:

```sh
ssh pi@nabaztag.local
```

Install the base packages that were needed during the fresh setup:

```sh
sudo apt-get update
sudo apt-get upgrade -y
sudo apt-get install -y \
  git gcc make raspberrypi-kernel-headers \
  python3 python3-venv python3-dev \
  postgresql postgresql-contrib libpq-dev \
  nginx gettext alsa-utils libasound2-dev libmpg123-0 mpg123 \
  libatlas-base-dev libopenblas-dev libblas3 liblapack3
```

Install the TagTagTag hardware drivers before running Pynab `install.sh`:

```sh
cd /opt
sudo git clone -b tagtagtag-sound https://github.com/pguyot/wm8960.git
sudo chown -R pi:pi wm8960
cd wm8960
make
sudo make install

cd /opt
sudo git clone https://github.com/pguyot/tagtagtag-ears.git
sudo chown -R pi:pi tagtagtag-ears
cd tagtagtag-ears
make
sudo make install
sudo reboot
```

RFID drivers are optional for the Wyoming voice setup. Install `cr14` for
the original TagTagTag RFID reader:

```sh
cd /opt
sudo git clone https://github.com/pguyot/cr14.git
sudo chown -R pi:pi cr14
cd cr14
make
sudo make install
sudo reboot
```

After reboot, verify:

```sh
ls -l /dev/rfid0
```

If the Nabaztag has the 2022 NFC board instead, install `st25r391x` from
https://github.com/pguyot/st25r391x.

## Install upstream Wyoming Satellite

Install Wyoming Satellite outside the Pynab virtual environment:

```sh
cd /opt
sudo git clone --branch v1.4.1 https://github.com/rhasspy/wyoming-satellite.git
sudo chown -R pi:pi wyoming-satellite
cd wyoming-satellite
script/setup
```

`wyoming-satellite.service` runs:

```sh
/opt/wyoming-satellite/script/run
```

The Pynab virtual environment is still used for the Nabaztag event handler
commands that drive LEDs and ears.

## Audio

The service uses the TagTagTag ALSA device explicitly:

```sh
arecord -D plughw:CARD=tagtagtagsound -r 16000 -c 1 -f S16_LE -t raw
aplay -D plughw:CARD=tagtagtagsound -r 22050 -c 1 -f S16_LE -t raw
```

This avoids relying on an ALSA `default` device.

## Home Assistant

Add the Nabaztag through the Wyoming Protocol integration:

```text
host: nabaztag.local or the Nabaztag IP
port: 10500
```

Configure the Assist pipeline so wake word detection runs on the Home
Assistant server, typically with openWakeWord.

## Button bridge

`wyoming-bridge.service` is optional. Set `HA_WEBHOOK_URL` in
`/opt/pynab/wyoming/wyoming.conf` if you want button events to trigger Home
Assistant automations.

## RFID webhooks

`nabwebhook.service` is useful for RFID-triggered Home Assistant automations.
When an RFID tag is configured for the webhook app, `nabwebhook` reads the URL
stored for that tag and calls it with HTTP GET.

Enable it with:

```sh
sudo systemctl enable --now nabwebhook.service
systemctl status nabwebhook.service --no-pager
```

Use the Pynab web RFID page to assign a Home Assistant webhook URL to a tag,
for example:

```text
http://homeassistant.local:8123/api/webhook/<webhook-id>
```

If a Home Assistant automation needs POST instead of GET, change
`nabwebhook/nabwebhook.py` to use `requests.post(...)`.

### RFID tag to Home Assistant automation

Create the Home Assistant automation first:

```text
Settings -> Automations & scenes -> Create automation
Create new automation -> Start with an empty automation
Add trigger -> Other triggers -> Webhook
```

Use settings like:

```text
Webhook ID: nabaztag_test_tag
Allowed methods: GET
Local only: enabled
```

Then add any Home Assistant action, for example turning on a light.

The webhook URL is:

```text
http://<home-assistant-ip>:8123/api/webhook/nabaztag_test_tag
```

In the Pynab web interface, open the RFID page, scan or select the tag, choose
the webhook app, and store that Home Assistant webhook URL on the tag. When the
Nabaztag scans the tag, `nabwebhook` calls the URL and Home Assistant runs the
automation.

`nabwebhook` currently performs HTTP GET, so the Home Assistant webhook trigger
must allow GET.

## Voice-focused service profile

The original Pi Zero has little CPU headroom. For a voice-focused setup, keep
these services enabled:

```text
nabd.service
nabweb.service
nabweb-boot.service
nabboot.service
nabsurprised.service
nabwebhook.service
wyoming-satellite.service
```

After installing the Home Assistant bridge, also keep `habridge.service`
enabled.

Keep `nabtaichid.service` and `nabclockd.service` only if their local sounds
and animations are still wanted. Any local Pynab service that plays audio can
compete with Wyoming for the sound card while Assist is listening or speaking.

If `nabclockd.service` stays enabled, open the clock settings in the Pynab web
interface and enable `Stay awake`. Scheduled sleep puts `nabd` into the
`asleep` state; Wyoming may still detect the wake word, but LED feedback and
bridge commands become unreliable until the rabbit wakes up again.

Disable unused/background services. Home Assistant can replace most of these
with lighter automations while the Nabaztag only handles speech, ears, LEDs,
RFID, and audio playback:

```sh
sudo systemctl disable --now \
  nab8balld.service \
  nabairqualityd.service \
  nabbookd.service \
  nabiftttd.service \
  nabmastodond.service \
  nabradio.service \
  nabweatherd.service \
  wyoming-bridge.service
```

Optional, if wake word reliability is more important than local clock/taichi:

```sh
sudo systemctl disable --now nabclockd.service nabtaichid.service
```

Re-enable a service later with:

```sh
sudo systemctl enable --now <service-name>.service
```

## Clearing stale LED animations

`nabweatherd` can leave visible blue/rain-style info animations. If the service
has since been disabled but the LEDs keep blinking, clear its info packets once:

```sh
python3 - <<'PY'
import json
import socket

for info_id in ("nabweatherd", "nabweatherd_rain"):
    with socket.create_connection(("127.0.0.1", 10543), timeout=5) as sock:
        packet = {"type": "info", "info_id": info_id}
        sock.sendall((json.dumps(packet) + "\r\n").encode("utf-8"))
PY
```

For new weather behavior, prefer a Home Assistant automation that sends a short
speech message and an explicit LED animation to the Nabaztag instead of running
`nabweatherd` locally.

## Home Assistant bridge

`habridge.service` exposes a small HTTP API on the Nabaztag that Home Assistant
can call. The bridge translates HTTP JSON requests into local `nabd` packets on
`127.0.0.1:10543`.

Install it after pulling this branch on the Nabaztag:

```sh
cd /opt/pynab
git fetch origin
git pull --ff-only
sudo cp habridge/habridge.service /lib/systemd/system/habridge.service
sudo systemctl daemon-reload
sudo systemctl enable --now habridge.service
```

Check it locally:

```sh
curl http://127.0.0.1:10544/health
```

Useful test calls:

```sh
curl -X POST http://127.0.0.1:10544/ears \
  -H 'Content-Type: application/json' \
  -d '{"left":10,"right":10}'

curl -X POST http://127.0.0.1:10544/leds/info \
  -H 'Content-Type: application/json' \
  -d '{"info_id":"ha_test","tempo":40,"colors":[{"left":"0000ff","center":"000000","right":"0000ff"},{"left":"000000","center":"000000","right":"000000"}]}'

curl -X POST http://127.0.0.1:10544/leds/clear \
  -H 'Content-Type: application/json' \
  -d '{"info_id":"ha_test"}'

curl -X POST http://127.0.0.1:10544/quiet/on
curl -X POST http://127.0.0.1:10544/quiet/off
```

The bridge supports:

```text
GET  /health
POST /leds/info
POST /leds/clear
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

`/packet` sends a raw `nabd` packet and is useful for experiments.
`/quiet` accepts `{"enabled":true}` or `{"enabled":false}`. `/quiet/on`
and `/quiet/off` are shortcuts.

Quiet mode is intended for media-center or evening use. It keeps `nabd`,
`nabwebhook`, `habridge`, and `wyoming-satellite` available, but it turns off
the `nabd` bottom status LED pulse and stops the local clock, surprise, and
taichi daemons. By default the bridge controls:

```text
nabclockd.service
nabsurprised.service
nabtaichid.service
```

Override that list in `habridge.conf` with `HABRIDGE_QUIET_SERVICES` if needed.
The same quiet-mode toggle is also available on the Pynab web interface home
page. Override the service list used by the web interface with
`NABWEB_QUIET_SERVICES` if needed.

Optional settings are in `/opt/pynab/habridge/habridge.conf`. Set
`HABRIDGE_TOKEN` if the bridge should require a bearer token or `?token=...`.
Set `HABRIDGE_HA_URL` and `HABRIDGE_HA_TOKEN` to enable `/tts/ha`.

Example Home Assistant `rest_command` entries:

```yaml
rest_command:
  nabaztag_ears:
    url: "http://nabaztag.local:10544/ears"
    method: post
    content_type: "application/json"
    payload: >
      {"left":{{ left }},"right":{{ right }}}

  nabaztag_leds:
    url: "http://nabaztag.local:10544/leds/info"
    method: post
    content_type: "application/json"
    payload: >
      {"info_id":"{{ info_id }}","tempo":{{ tempo }},"colors":{{ colors }}}

  nabaztag_clear_leds:
    url: "http://nabaztag.local:10544/leds/clear"
    method: post
    content_type: "application/json"
    payload: >
      {"info_id":"{{ info_id }}"}
```

A fuller Home Assistant package is available in:

```text
habridge/home-assistant-package.yaml
```

Copy it into Home Assistant, for example:

```text
/config/packages/nabaztag.yaml
```

If packages are not enabled yet, add this to Home Assistant
`configuration.yaml`:

```yaml
homeassistant:
  packages: !include_dir_named packages
```

Then check the Home Assistant configuration and restart Home Assistant.

The package adds scripts for:

```text
script.nabaztag_move_ears
script.nabaztag_led_effect
script.nabaztag_clear_led_effect
script.nabaztag_sleep
script.nabaztag_wakeup
script.nabaztag_quiet_on
script.nabaztag_quiet_off
script.nabaztag_show_weather
```

`script.nabaztag_show_weather` always drives ears and weather LEDs through the
bridge. Its speech step uses the bridge `/tts/ha` endpoint, so the Nabaztag
does not need to appear as a Home Assistant media player. Pass `tts_entity`
for speech. The package sends raw weather values to `/weather/say`, and the
bridge prepares a German weather sentence before asking Home Assistant TTS for
an MP3. `/weather/say` attaches a generated smooth LED choreography to the
audio command and moves the ears inside the same choreography, so active
weather LEDs keep running while the rabbit speaks and the Home Assistant script
only needs one bridge call. If the Home Assistant weather entity exposes
`wind_speed`, the spoken sentence also includes rounded wind speed.

To enable bridge speech, create a long-lived access token in Home Assistant and
set these values in `/opt/pynab/habridge/habridge.conf`:

```sh
HABRIDGE_HA_URL=http://<home-assistant-lan-ip>:8123
HABRIDGE_HA_TOKEN=<long-lived-access-token>
```

Keep this token out of git if you later edit files on the Nabaztag.

Restart the bridge after changing the file:

```sh
sudo systemctl restart habridge.service
```

Test bridge speech from the Nabaztag:

```sh
curl -X POST http://127.0.0.1:10544/tts/ha \
  -H 'Content-Type: application/json' \
  -d '{"engine_id":"tts.your_tts_entity","message":"The weather bridge is working."}'
```

Test bridge weather speech from the Nabaztag:

```sh
curl -X POST http://127.0.0.1:10544/weather/say \
  -H 'Content-Type: application/json' \
  -d '{"engine_id":"tts.your_tts_entity","condition":"rainy","temperature":"12","unit":"°C","language":"de"}'
```

If `/tts/ha` returns `status: ok` but the speaker only crackles or stays silent,
install the native MP3 decoder used by Pynab:

```sh
sudo apt-get update
sudo apt-get install -y libmpg123-0 mpg123
```

Verify the decoder from the Pynab virtual environment:

```sh
/opt/pynab/venv/bin/python - <<'PY'
from mpg123 import Mpg123
mp3 = Mpg123("/tmp/ha_tts_test.mp3")
print(mp3.get_format())
print("frames ok")
PY
```
