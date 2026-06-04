import time
import unittest

from nabd.leds import Led, LedsSoft


class LedsInterface(LedsSoft):
    PULSING_RATE = 0.01
    PULSING_STEPS = 4

    def __init__(self):
        super().__init__()
        self.calls = []

    def do_set(self, led, red, green, blue):
        self.calls.append(("do_set", led, red, green, blue))

    def do_show(self):
        self.calls.append("do_show")


class TestLeds(unittest.TestCase):
    def setUp(self):
        self.leds = LedsInterface()

    def tearDown(self):
        self.leds.stop()

    def test_set1(self):
        self.leds.set1(0, 10, 20, 30)
        time.sleep(0.1)
        self.assertEqual(
            self.leds.calls, [("do_set", 0, 10, 20, 30), "do_show"]
        )

    def test_setall(self):
        self.leds.setall(10, 20, 30)
        time.sleep(0.1)
        self.assertEqual(
            self.leds.calls,
            [
                ("do_set", Led.BOTTOM, 10, 20, 30),
                ("do_set", Led.RIGHT, 10, 20, 30),
                ("do_set", Led.CENTER, 10, 20, 30),
                ("do_set", Led.LEFT, 10, 20, 30),
                ("do_set", Led.NOSE, 10, 20, 30),
                "do_show",
            ],
        )

    def test_pulse(self):
        self.leds.pulse(Led.BOTTOM, 40, 80, 120)
        time.sleep(0.2)
        self.assertEqual(
            self.leds.calls[:14],
            [
                ("do_set", Led.BOTTOM, 0, 0, 0),
                "do_show",
                ("do_set", Led.BOTTOM, 10, 20, 30),
                "do_show",
                ("do_set", Led.BOTTOM, 20, 40, 60),
                "do_show",
                ("do_set", Led.BOTTOM, 30, 60, 90),
                "do_show",
                ("do_set", Led.BOTTOM, 40, 80, 120),
                "do_show",
                ("do_set", Led.BOTTOM, 30, 60, 90),
                "do_show",
                ("do_set", Led.BOTTOM, 20, 40, 60),
                "do_show",
            ],
        )
