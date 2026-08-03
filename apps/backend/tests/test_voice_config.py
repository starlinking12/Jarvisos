from __future__ import annotations

from jarvis_backend.voice.config import VoiceSettings, get_voice_settings


def test_default_voice_settings_are_disabled_by_default() -> None:
    settings = VoiceSettings()
    assert settings.enabled is False


def test_default_audio_config_matches_project_standard() -> None:
    settings = VoiceSettings()
    audio_config = settings.audio_config()

    assert audio_config.sample_rate == 16_000
    assert audio_config.channels == 1
    assert audio_config.frame_duration_ms == 20


def test_default_wake_word_config_has_sane_defaults() -> None:
    settings = VoiceSettings()
    wake_config = settings.wake_word_config()

    assert "jarvis" in wake_config.wake_words
    assert 0.0 <= wake_config.sensitivity <= 1.0
    assert wake_config.consecutive_frames_required >= 1


def test_default_piper_voice_mappings_include_default_voice() -> None:
    settings = VoiceSettings()
    mappings = settings.piper_voice_mappings()

    voice_ids = {mapping.voice_id for mapping in mappings}
    assert settings.piper.default_voice_id in voice_ids


def test_get_voice_settings_returns_defaults_when_no_json_given() -> None:
    settings = get_voice_settings(None)
    assert settings.enabled is False


def test_get_voice_settings_parses_json_override() -> None:
    raw_json = '{"enabled": true, "vad": {"aggressiveness": 3}}'
    settings = get_voice_settings(raw_json)

    assert settings.enabled is True
    assert settings.vad.aggressiveness == 3


def test_voice_settings_validates_devices_section() -> None:
    settings = VoiceSettings.model_validate(
        {"devices": {"sample_rate": 48000, "input_device_index": 2}}
    )

    assert settings.devices.sample_rate == 48000
    assert settings.devices.input_device_index == 2
