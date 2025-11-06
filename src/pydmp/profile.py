from dataclasses import dataclass


@dataclass
class UserProfile:
    """User profile record (not encrypted)."""

    number: str
    areas_mask: str
    access_areas_mask: str
    output_group: str
    menu_options: str
    rearm_delay: str
    name: str
