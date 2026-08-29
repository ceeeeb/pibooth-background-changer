# -*- coding: utf-8 -*-

"""Tests of the platform detection driving the model choice."""

import unittest
from unittest import mock

import pibooth_background_changer as plugin


def platform_for(model):
    """Return the platform detected for the given device tree content."""
    if model is None:
        with mock.patch('builtins.open', side_effect=IOError):
            return plugin._detect_platform()
    with mock.patch('builtins.open', mock.mock_open(read_data=model)):
        return plugin._detect_platform()


class DetectPlatformTest(unittest.TestCase):

    def test_khadas_vim4_is_recognised(self):
        self.assertEqual(platform_for("Khadas VIM4\x00"), 'khadas_vim4')

    def test_raspberry_pi_models_are_told_apart(self):
        self.assertEqual(platform_for("Raspberry Pi 5 Model B Rev 1.0\x00"), 'raspberry_pi_5')
        self.assertEqual(platform_for("Raspberry Pi 4 Model B Rev 1.1\x00"), 'raspberry_pi_4')
        self.assertEqual(platform_for("Raspberry Pi Zero 2 W\x00"), 'raspberry_pi')

    def test_unknown_board_is_not_taken_for_a_desktop(self):
        self.assertEqual(platform_for("Some Unknown SBC\x00"), 'embedded_board')

    def test_machine_without_device_tree_is_a_desktop(self):
        self.assertEqual(platform_for(None), 'desktop')


class RecommendationTest(unittest.TestCase):

    def test_every_board_gets_the_light_model(self):
        for platform in ('khadas_vim4', 'raspberry_pi_4', 'raspberry_pi_5', 'embedded_board'):
            self.assertEqual(plugin._get_recommended_model(platform), 'silueta')
            self.assertEqual(plugin._get_recommended_resolution(platform), (640, 480))

    def test_desktop_gets_the_heavy_model(self):
        self.assertEqual(plugin._get_recommended_model('desktop'), 'isnet-general-use')
        self.assertEqual(plugin._get_recommended_resolution('desktop'), (1280, 720))


if __name__ == '__main__':
    unittest.main()
