# Home Assistant Wyoming Satellite

This setup keeps Pynab on the Nabaztag and runs Wyoming Satellite from a
separate upstream checkout. Home Assistant handles wake word recognition,
speech-to-text, Assist, and text-to-speech.

The original Pi Zero should not run wake word recognition locally.

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
