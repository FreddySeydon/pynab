# Linux Voice Assistant integration

This replaces the deprecated `wyoming-satellite` service with
OHF-Voice's Linux Voice Assistant (LVA).

LVA speaks the ESPHome protocol on port `6053`. After it is running, add it
to Home Assistant with the ESPHome integration and use the generated
`assist_satellite.*` entity id in `linux_voice_assistant.conf`.

## Hardware expectation

LVA currently targets `linux/amd64` and `linux/aarch64`, Python 3.11/3.12,
and at least 512 MB RAM. A Raspberry Pi Zero 2 W with a 64-bit OS is a
realistic minimum for local wake word detection. A first-generation Pi Zero
or the 2018 board without a microphone is not a realistic target for this
service.

## Install LVA

Install LVA separately under `/opt/linux-voice-assistant` using the upstream
bare-metal instructions:

```sh
cd /opt
sudo git clone https://github.com/OHF-Voice/linux-voice-assistant.git
sudo chown -R pi:pi linux-voice-assistant
cd linux-voice-assistant
script/setup --cxxflags="-O1 -g0" --makeflags="-j1"
sudo usermod -a -G audio pi
```

PipeWire or PulseAudio must be running for the same user as the service.

## Configure

Edit `linux_voice_assistant.conf`:

```sh
sudo nano /opt/pynab/linux_voice_assistant/linux_voice_assistant.conf
```

Set `HA_URL`, `HA_ACCESS_TOKEN`, and
`HA_ASSIST_SATELLITE_ENTITY_ID` if you want the Nabaztag LEDs/ears to follow
the Home Assistant Assist satellite state.

The bridge maps Home Assistant states like this:

| Home Assistant state | Nabaztag state |
| --- | --- |
| `idle` | LEDs off, ears reset |
| `listening` | blue center LED, ears forward |
| `processing` | blinking white center LED |
| `responding` | blinking green center LED, ears moved |
| unavailable/error states | blinking red center LED |

## Services

These files are installed by Pynab's `install.sh`:

```sh
sudo systemctl start linux-voice-assistant.service
sudo systemctl start nabaztag-assist-bridge.service
sudo systemctl start nabaztag-assist-button-bridge.service
```

The LVA service is skipped until the upstream
`/opt/linux-voice-assistant/docker-entrypoint.sh` exists.
