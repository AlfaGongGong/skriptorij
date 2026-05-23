"""Compatibility wrapper around config.ai_config provider profile data."""

from config.ai_config import (
    ProviderProfile,
    PROVIDER_PROFILES,
    effective_rpd_with_keys,
    effective_rpm_with_keys,
    get_cooldown_429,
    get_min_gap,
    get_profile,
    get_quality_tier,
    get_rpd_safe,
    get_rpm_safe,
    is_preferred_for_role,
    print_fleet_capacity,
    should_avoid_for_role,
)

__all__ = [
    'ProviderProfile',
    'PROVIDER_PROFILES',
    'effective_rpd_with_keys',
    'effective_rpm_with_keys',
    'get_cooldown_429',
    'get_min_gap',
    'get_profile',
    'get_quality_tier',
    'get_rpd_safe',
    'get_rpm_safe',
    'is_preferred_for_role',
    'print_fleet_capacity',
    'should_avoid_for_role',
]
