# Nabaztag Home Assistant Exploration Notes

These notes capture the exploration that turned an old Nabaztag into a working
Home Assistant voice satellite. They are intentionally broader than a setup
guide so they can be used later as raw material for a blog post.

## The Starting Point

The project started with a practical problem: Wyoming Satellite had been
integrated into a Pynab-based Nabaztag setup, but the first approach was fragile
on the original Pi Zero hardware. The goal was not to build a general-purpose
Linux voice assistant on the rabbit. The goal was to make the rabbit useful in a
living room: listen for Home Assistant wake words, speak responses, move its
ears, use LEDs expressively, and react to RFID tags.

The first alternative considered was `OHF-Voice/linux-voice-assistant`. That
project looked more modern than the abandoned/awkward pieces around older voice
stacks, but the Nabaztag hardware was the deciding factor. An original Pi Zero
is not a good place to run a complete voice assistant, especially wake word
recognition. The better architectural split was:

- Home Assistant server: wake word, STT, Assist logic, TTS.
- Nabaztag: microphone stream, speaker, ears, LEDs, RFID, and local web/bridge
  endpoints.

This made the rabbit a charming I/O satellite instead of a tiny overloaded
computer trying to understand speech locally.

## Hardware Reality

The working device is an original Nabaztag with a TagTagTag board and an
original Pi Zero. That matters because it defines the limits:

- ARMv6 32-bit.
- Very limited CPU headroom.
- Python version constraints.
- Driver installation depends on matching kernel headers.
- The sound card is the TagTagTag WM8960 device.

There was discussion about replacing the Pi with a Pi Zero 2 W, but confidence
was not high enough. Pynab compatibility on newer hardware was uncertain, and a
previous Wyoming experience on a Zero 2 W had still been disappointing. The
safer path was to make the existing Pi Zero do less work, not ask it to do more.

The TagTagTag board microphones technically work, but they sit in a bad acoustic
position for the old Nabaztag case. With the case off, recordings are usable but
include a high-frequency noise. With the case on, the sound is muffled because
the microphone holes do not line up with the old case opening. This remains one
of the biggest hardware tradeoffs.

Options that came up:

- Add holes or an acoustic channel near the board microphones.
- Try to reduce gain/noise in ALSA or mixer settings.
- Find a tiny USB microphone that can fit internally.
- Investigate whether the original microphone can be wired to the audio codec,
  if suitable pads/connectors exist.

For now, the software works; microphone quality is the weak spot.

## The OS Rebuild

The setup was rebuilt on a fresh SD card. Raspberry Pi OS Legacy 32-bit Lite was
chosen because the original Pi Zero needs 32-bit ARMv6 support and Pynab works
with Python 3.9 on that base.

There were several operational details that mattered:

- If Raspberry Pi Imager cannot set hostname, SSH, user, and Wi-Fi, those can be
  configured manually on the boot partition or after first SSH login.
- Hostname should be changed from `raspberrypi` to `nabaztag`.
- SSH through `nabaztag.local` depends on mDNS and the device being on the same
  usable LAN, not an isolated guest network.
- The `ssh` marker file on the boot partition is consumed on boot, so it
  disappearing is normal.
- A full SD card image backup after the working setup was a very good idea.

The network detour was a reminder that a voice satellite is still a network
appliance. Guest Wi-Fi, mDNS, IPv6 link-local addresses, and blocked SSH can
look like software failures when the actual issue is network placement.

## Driver Gauntlet

Pynab installation stopped several times because required packages or drivers
were missing. The final working setup documented these as prerequisites instead
of letting the installer discover them one failure at a time.

Important pieces:

- `wm8960` TagTagTag sound driver.
- `tagtagtag-ears` driver.
- `cr14` RFID driver.
- PostgreSQL.
- Nginx.
- GNU gettext tools for `msgfmt`.
- ALSA development headers for mixer compilation.
- BLAS/OpenBLAS/Atlas libraries for old NumPy/Snips dependencies.
- `libmpg123-0` and `mpg123` for MP3 decoding inside Pynab.

The installation sequence was not glamorous, but it was instructive. Old
hardware plus old Python packages often fail for missing native libraries rather
than for obvious Python reasons.

## Python Compatibility Surprises

The first attempt to install modern voice code on the old Pynab environment ran
into Python 3.7 limitations:

- `typing.Final` was missing.
- Some packages required newer `setuptools-scm`.
- A Wyoming Satellite file used the walrus operator, which Python 3.7 cannot
  parse.
- PyPI/piwheels availability on ARMv6 constrained what could be installed.

The Wyoming Satellite README said Python 3.7+, but the actual package state did
not behave that way for the versions being installed. This was not worth fighting
inside Pynab's venv.

The chosen solution was to install upstream Wyoming Satellite separately at:

```text
/opt/wyoming-satellite
```

and let Pynab keep its own venv for rabbit behavior. That separation reduced the
risk that voice dependencies would break Pynab.

## The Working Voice Architecture

The final voice path is:

1. The Nabaztag runs upstream Wyoming Satellite.
2. Wyoming records raw audio from the TagTagTag ALSA input at 16000 Hz mono.
3. Home Assistant connects to the Nabaztag's Wyoming endpoint on port 10500.
4. Home Assistant runs wake word detection and Assist.
5. TTS output is fetched by the bridge and played through `nabd`.

The important part is that wake word recognition happens on the Home Assistant
server, not on the rabbit. CPU on the Nabaztag still spikes, but the device is no
longer trying to do the most expensive inference work.

The explicit audio commands matter:

```sh
arecord -D plughw:CARD=tagtagtagsound -r 16000 -c 1 -f S16_LE -t raw
aplay -D plughw:CARD=tagtagtagsound -r 22050 -c 1 -f S16_LE -t raw
```

The output rate was corrected to 22050 Hz after audio sounded too low at 16000
Hz.

## Service Triage

Pynab ships many charming services, but the original Pi Zero is not a good place
to run all of them while also acting as a voice satellite.

Services that were disabled or de-prioritized:

- 8-ball.
- Air quality.
- Books.
- IFTTT.
- Mastodon.
- Radio.
- Weather.
- Old local Wyoming bridge.

Services kept because they are useful or charming:

- Main daemon.
- Web UI.
- Webhook/RFID daemon.
- Clock, surprise, and taichi, when not in quiet mode.
- Wyoming Satellite.
- Home Assistant bridge.

This was not just about CPU usage. Local services can also play audio or animate
LEDs at awkward times. For a living-room voice assistant, predictable behavior is
more important than every old service being active.

## Sleep Was A Problem

The rabbit went to sleep because of the clock settings in the web UI. After
that, wake word behavior became unreliable and LED feedback did not always run
even when wake word detection triggered. Waking the rabbit helped, but the
experience made it clear that scheduled sleep and a voice satellite are in
tension.

A `Stay awake` clock setting was added so the clock service can remain installed
without putting the voice satellite into an asleep state.

## Home Assistant Bridge

The bridge was added because Home Assistant needs a simple way to tell the
rabbit to move ears, blink LEDs, speak, sleep/wake, and enter quiet mode.

The bridge is intentionally small:

- HTTP JSON in.
- `nabd` packet out.
- No Home Assistant custom integration required.

This avoided prematurely building a full Home Assistant entity model. The bridge
and package approach was enough to make the device useful quickly.

The bridge endpoint lives at:

```text
http://nabaztag.local:10544
```

Important bridge behavior:

- `/health` proves the bridge can talk to `nabd`.
- `/ears` moves ears.
- `/leds/info` starts a named LED info animation.
- `/leds/clear` clears a named info animation.
- `/leds/reset` sends a direct all-LEDs-off command.
- `/tts/ha` uses Home Assistant TTS and plays the result through the rabbit.
- `/weather/say` builds a weather sentence, asks Home Assistant for TTS, and
  sends speech plus LEDs plus ears as one active choreography.
- `/quiet/on` and `/quiet/off` control living-room quiet mode.

The bridge also made it possible to keep Home Assistant automations expressive
without having to understand Pynab internals in every automation.

## Weather Became A Good Example

The old local Pynab weather service was too heavy and visually aggressive. It
also did not fit the new architecture. Weather became a useful test case for
offloading logic to Home Assistant while using the rabbit for expression.

The final weather flow:

1. Home Assistant script reads weather entity state and attributes.
2. It calls the bridge `/weather/say` endpoint.
3. The bridge rounds temperature for natural speech.
4. The bridge includes wind speed when available.
5. The bridge creates a German weather sentence.
6. Home Assistant TTS creates an MP3.
7. The bridge sends one active `nabd` command containing audio, LEDs, and ears.

One subtle improvement was moving the LEDs out of idle `info` animations for
active weather playback. Idle info animations stop while audio plays, which is
fine for background status but bad for an active weather response. A combined
choreography lets the LEDs continue while the rabbit speaks.

## LEDs And Living-Room UX

The device has a lot of personality, but too much blinking is annoying in a
living room. Several LED-related changes came from that:

- The constant blue front LED status was investigated and cleared.
- The fuchsia bottom status pulse was made smoother.
- Quiet mode can disable the fuchsia pulse entirely.
- A reset endpoint was added for stuck LEDs.
- Active weather LEDs were changed to smoother choreography-style effects.

The key UX lesson: the rabbit can be expressive, but idle effects must be calm
and optional.

## Quiet Mode

Quiet mode is for situations like watching media. The user wanted the rabbit to
keep listening for voice commands and accepting RFID tags, but stop interrupting
with local clock, surprise, taichi, and the fuchsia status pulse.

Quiet mode currently:

- Turns off `nabd` status pulsing.
- Stops configured local services.
- Keeps `nabd`, `nabwebhook`, `habridge`, and `wyoming-satellite` alive.
- Can be toggled from the web UI.
- Can be toggled from Home Assistant.

This makes the rabbit feel more like a controllable appliance and less like an
unpredictable toy.

## RFID Was Surprisingly Useful

The CR14 RFID driver was installed and worked. `nabwebhook.service` lets tags
call URLs, and Home Assistant webhook automations can accept GET requests.

That immediately made it possible to use physical cards or objects to trigger
Home Assistant actions, such as starting media center scenes.

The current approach stores a webhook URL per tag in Pynab. A future approach
could send the tag UID to one Home Assistant webhook and let Home Assistant route
actions centrally.

## Reliability Notes

The system worked after reboot and survived normal use, but there was at least
one reliability issue:

- Wyoming logged `BrokenPipeError`.
- It also logged missed ping responses and reconnects.
- `arecord` tests were clean when Wyoming was stopped.
- CPU was not obviously pegged at the time.

This suggests the failure might be stream timing, Home Assistant-side load,
network timing, or a long-running Wyoming state issue rather than a simple sound
card failure. It is not resolved.

For future debugging, useful checks are:

- `journalctl -u wyoming-satellite.service -f`
- Home Assistant Wyoming integration logs.
- A clean local `arecord` capture while Wyoming is stopped.
- Network stability between Home Assistant and the rabbit.
- Whether the problem appears only after long uptime.

## What Worked Well

The biggest successful decision was to reduce what the Nabaztag itself does.
The rabbit is good at:

- Being visible.
- Moving ears.
- Lighting LEDs.
- Playing short sounds.
- Accepting RFID tags.
- Streaming microphone audio.

It is not good at:

- Running modern Python voice stacks in the Pynab venv.
- Wake word inference.
- Heavy local services while also streaming audio.
- Acting as a fully general assistant runtime.

Once Home Assistant became the brain and the rabbit became the expressive I/O
body, the project became much more stable.

## Open Questions

Good future blog/project angles:

- How much of the original Nabaztag personality should remain local?
- Should Home Assistant eventually get a real Nabaztag integration?
- Is a media-player entity worth it, or is the bridge enough?
- Can the microphone quality be fixed without major hardware surgery?
- Should all old Pynab services be replaced by Home Assistant scripts?
- Can RFID become a first-class Home Assistant control surface?
- How much idle animation is charming, and when does it become noise?

## Backlog

Potential next steps:

- Diagnose long-running Wyoming overrun/reconnect behavior.
- Improve microphone acoustics.
- Build a better RFID dispatch model.
- Add richer weather forecasts, including evening/night summaries.
- Add more Home Assistant scripts for media-center scenes.
- Consider a proper Home Assistant custom integration after the bridge API
  stabilizes.
- Decide whether quiet mode should restore exact previous service states.
- Keep documenting package installs and device-specific setup whenever a new
  failure is discovered.

## One-Sentence Summary

The successful version of this project is not a Nabaztag that runs a whole voice
assistant; it is a Nabaztag that lets Home Assistant borrow its body.
