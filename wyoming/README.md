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
  nginx gettext alsa-utils libasound2-dev \
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

RFID drivers are optional for the Wyoming voice setup and can be installed
later if tag reading/writing is needed.

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
