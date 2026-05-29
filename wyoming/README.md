# Home Assistant Wyoming satellite

This integration keeps the Nabaztag on its existing Raspberry Pi Zero
hardware and streams microphone audio to Home Assistant. Wake word
detection, STT, Assist, and TTS run on the Home Assistant server.

The Nabaztag does not run local wake word recognition in this setup.

## Home Assistant

Install and configure these integrations/add-ons on Home Assistant:

- Wyoming Protocol integration
- openWakeWord
- an STT provider
- a TTS provider

Add the Nabaztag as a Wyoming satellite at:

```text
nabaztag.local:10500
```

## Nabaztag services

`wyoming-satellite.service` streams 16 kHz mono raw PCM from `arecord` and
plays returned TTS audio through `aplay`.

`wyoming-bridge.service` keeps the existing button webhook behavior. Set
`HA_WEBHOOK_URL` in `wyoming.conf` if you want Home Assistant automations
for single, double, or long button presses.

## Notes

VAD is intentionally not enabled. Wyoming Satellite's VAD path is not
reliable on 32-bit Raspberry Pi OS, and this hardware is `armv6l`.
