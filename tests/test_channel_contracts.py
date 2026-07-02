"""
Contract tests: verify that every Channel subclass implements the required interface.

This test uses reflection to discover all Channel subclasses and asserts that
each one properly defines ``name``, ``tier``, ``backends`` and implements all
four abstract methods.
"""

from __future__ import annotations

import pytest

from social_dive.channels import Channel, ChannelTier
from social_dive.doctor import _discover_channels, get_registered_channels


@pytest.fixture(autouse=True, scope="module")
def discover():
    _discover_channels()


def _get_all_channel_classes() -> list[type[Channel]]:
    """Get all registered Channel subclasses."""
    return get_registered_channels()


class TestChannelContracts:
    """Every channel must satisfy the Channel interface contract."""

    def test_at_least_one_channel_registered(self) -> None:
        channels = _get_all_channel_classes()
        assert len(channels) > 0, "No channels registered — did auto-discovery fail?"

    @pytest.mark.parametrize("cls", _get_all_channel_classes(), ids=lambda c: c.name)
    def test_has_name(self, cls: type[Channel]) -> None:
        assert hasattr(cls, "name"), f"{cls.__name__} missing 'name'"
        assert isinstance(cls.name, str), f"{cls.__name__}.name must be a str"
        assert len(cls.name) > 0, f"{cls.__name__}.name is empty"

    @pytest.mark.parametrize("cls", _get_all_channel_classes(), ids=lambda c: c.name)
    def test_has_tier(self, cls: type[Channel]) -> None:
        assert hasattr(cls, "tier"), f"{cls.__name__} missing 'tier'"
        assert isinstance(cls.tier, ChannelTier), f"{cls.__name__}.tier must be a ChannelTier"

    @pytest.mark.parametrize("cls", _get_all_channel_classes(), ids=lambda c: c.name)
    def test_has_backends(self, cls: type[Channel]) -> None:
        assert hasattr(cls, "backends"), f"{cls.__name__} missing 'backends'"
        assert isinstance(cls.backends, list), f"{cls.__name__}.backends must be a list"
        assert len(cls.backends) > 0, f"{cls.__name__}.backends is empty"

    @pytest.mark.parametrize("cls", _get_all_channel_classes(), ids=lambda c: c.name)
    def test_implements_can_handle(self, cls: type[Channel]) -> None:
        instance = cls()
        assert callable(getattr(instance, "can_handle", None))

    @pytest.mark.parametrize("cls", _get_all_channel_classes(), ids=lambda c: c.name)
    def test_implements_read(self, cls: type[Channel]) -> None:
        instance = cls()
        assert callable(getattr(instance, "read", None))

    @pytest.mark.parametrize("cls", _get_all_channel_classes(), ids=lambda c: c.name)
    def test_implements_search(self, cls: type[Channel]) -> None:
        instance = cls()
        assert callable(getattr(instance, "search", None))

    @pytest.mark.parametrize("cls", _get_all_channel_classes(), ids=lambda c: c.name)
    def test_implements_check(self, cls: type[Channel]) -> None:
        instance = cls()
        assert callable(getattr(instance, "check", None))

    @pytest.mark.parametrize("cls", _get_all_channel_classes(), ids=lambda c: c.name)
    def test_unique_name(self, cls: type[Channel]) -> None:
        """No two channels should share the same name."""
        all_names = [c.name for c in _get_all_channel_classes()]
        assert all_names.count(cls.name) == 1, f"Duplicate channel name: '{cls.name}'"
