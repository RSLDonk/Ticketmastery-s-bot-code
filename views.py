"""Compatibility exports for view classes split into focused modules.

New code should import from ``setup``, ``panel``, ``categories``,
``transcripts``, or ``ticket_controls`` directly.
"""

from .categories import (
    AddCategoryModal,
    AddCategoryRolePicker,
    AddCategoryRoleView,
    CategoryView,
    DeleteCategoryModal,
    EditCategoryModal,
    TicketCategorySelect,
    build_categories_embed,
    ticket_creation_cooldowns,
)
from .panel import (
    PanelDescModal,
    PanelManagerView,
    build_panel_embed,
    build_panel_view,
    send_ticket_panel,
)
from .setup import (
    SETUP_VIEW_TIMEOUT_SECONDS,
    LogChannelModal,
    LogChannelPicker,
    LogChannelSelectView,
    SettingsView,
    SetupMenu,
    SetupView,
    StaffRoleModal,
    StaffRolePicker,
    StaffRoleSelectView,
    build_setup_embed,
    refresh_setup_panel,
)
from .ticket_controls import (
    CloseConfirmView,
    CloseReasonModal,
    TicketButtons,
    build_close_confirmation_embed,
)
from .transcripts import TranscriptView, build_settings_embed


__all__ = [
    "SETUP_VIEW_TIMEOUT_SECONDS",
    "AddCategoryModal",
    "AddCategoryRolePicker",
    "AddCategoryRoleView",
    "CategoryView",
    "CloseConfirmView",
    "CloseReasonModal",
    "DeleteCategoryModal",
    "EditCategoryModal",
    "LogChannelModal",
    "LogChannelPicker",
    "LogChannelSelectView",
    "PanelDescModal",
    "PanelManagerView",
    "SettingsView",
    "SetupMenu",
    "SetupView",
    "StaffRoleModal",
    "StaffRolePicker",
    "StaffRoleSelectView",
    "TicketButtons",
    "TicketCategorySelect",
    "TranscriptView",
    "build_categories_embed",
    "build_close_confirmation_embed",
    "build_panel_embed",
    "build_panel_view",
    "build_settings_embed",
    "build_setup_embed",
    "refresh_setup_panel",
    "send_ticket_panel",
    "ticket_creation_cooldowns",
]
