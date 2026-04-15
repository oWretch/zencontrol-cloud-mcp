"""Pydantic models for ZenControl Cloud REST API responses and commands.

These models represent the data structures returned by the ZenControl Cloud API
for DALI-2 lighting control systems, including sites, gateways, devices, groups,
and command payloads.
"""

from __future__ import annotations

from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


# ---------------------------------------------------------------------------
# Helper enums
# ---------------------------------------------------------------------------


class ScopeType(StrEnum):
    """Scope types used to filter resources in tool parameters."""

    SITE = "site"
    FLOOR = "floor"
    MAP = "map"
    TENANCY = "tenancy"
    CONTROL_SYSTEM = "control_system"
    GATEWAY = "gateway"
    ZONE = "zone"


class CommandTargetType(StrEnum):
    """Target types for DALI commands."""

    SITE = "site"
    TENANCY = "tenancy"
    FLOOR = "floor"
    MAP = "map"
    ZONE = "zone"
    CONTROL_SYSTEM = "control_system"
    GATEWAY = "gateway"
    DEVICE_LOCATION = "device_location"
    DEVICE = "device"
    ECG = "ecg"
    ECD = "ecd"
    GROUP = "group"


class DaliCommandType(StrEnum):
    """DALI command types supported by the ZenControl API."""

    OFF = "off"
    RECALL_MAX = "recallMax"
    RECALL_MIN = "recallMin"
    STEP_UP = "stepUp"
    STEP_UP_ON = "stepUpOn"
    STEP_DOWN = "stepDown"
    STEP_DOWN_OFF = "stepDownOff"
    DIM_UP = "dimUp"
    DIM_DOWN = "dimDown"
    SET_LEVEL = "setLevel"
    GO_TO_SCENE = "goToScene"
    GO_TO_PROFILE = "goToProfile"
    RETURN_TO_SCHEDULED_PROFILE = "returnToScheduledProfile"
    COLOUR_TEMPERATURE = "colourTemperature"
    COLOUR_XY = "colourXY"
    COLOUR_RGBWAF = "colourRgbwaf"
    IDENTIFY = "identify"
    OVERRIDE_TARGET = "overrideTarget"


# ---------------------------------------------------------------------------
# Base / shared types
# ---------------------------------------------------------------------------


class DaliId(BaseModel):
    """Composite DALI identifier consisting of a GTIN and serial number.

    Used as the identifier for gateways, bus units, and ECG/ECD components.
    In URL paths, represented as ``{gtin}-{serial}``.
    """

    model_config = ConfigDict(populate_by_name=True)

    gtin: int
    serial: str


class StringField(BaseModel):
    """Syncable string field wrapper from the ZenControl API.

    Wraps a string value with synchronisation state and optional error info.
    """

    model_config = ConfigDict(populate_by_name=True)

    value: str | None = None
    state: str | None = None
    error: str | None = None


class IntField(BaseModel):
    """Syncable integer field wrapper from the ZenControl API.

    Wraps an integer value with synchronisation state and optional error info.
    """

    model_config = ConfigDict(populate_by_name=True)

    value: int | None = None
    state: str | None = None
    error: str | None = None


class StatusField(BaseModel):
    """Syncable status field indicating ACTIVE or INACTIVE state."""

    model_config = ConfigDict(populate_by_name=True)

    value: Literal["ACTIVE", "INACTIVE"] | None = None
    state: str | None = None
    error: str | None = None


class GroupTypeField(BaseModel):
    """Syncable group type field for DALI group classification."""

    model_config = ConfigDict(populate_by_name=True)

    value: Literal["UNKNOWN", "STANDARD", "SCENE", "SYSTEM", "PROTECTED"] | None = None
    state: str | None = None
    error: str | None = None


# ---------------------------------------------------------------------------
# Composite ID types
# ---------------------------------------------------------------------------


class GroupId(BaseModel):
    """Composite identifier for a DALI group.

    Combines the gateway identifier with a group number (0-15).
    """

    model_config = ConfigDict(populate_by_name=True)

    gateway_id: DaliId = Field(alias="gatewayId")
    group_number: int = Field(alias="groupNumber", ge=0, le=15)


class DeviceId(BaseModel):
    """Composite identifier for a DALI bus device.

    Combines the gateway identifier with the bus unit identifier.
    """

    model_config = ConfigDict(populate_by_name=True)

    gateway_id: DaliId = Field(alias="gatewayId")
    bus_unit_id: DaliId = Field(alias="busUnitId")


class EcgId(BaseModel):
    """Composite identifier for an Emergency Control Gear (ECG).

    Combines gateway, bus unit, and a logical index.
    """

    model_config = ConfigDict(populate_by_name=True)

    gateway_id: DaliId = Field(alias="gatewayId")
    bus_unit_id: DaliId = Field(alias="busUnitId")
    logical_index: int = Field(alias="logicalIndex")


# ---------------------------------------------------------------------------
# Resource models
# ---------------------------------------------------------------------------


class Address(BaseModel):
    """Physical address of a site."""

    model_config = ConfigDict(populate_by_name=True)

    country: str | None = None
    admin_area: str | None = Field(default=None, alias="adminArea")
    locality: str | None = None
    dependent_locality: str | None = Field(default=None, alias="dependentLocality")
    post_code: str | None = Field(default=None, alias="postCode")
    sorting_code: str | None = Field(default=None, alias="sortingCode")
    street: str | None = None


class GeographicLocation(BaseModel):
    """Geographic coordinates for a site."""

    model_config = ConfigDict(populate_by_name=True)

    latitude: float | None = None
    longitude: float | None = None


class Site(BaseModel):
    """A ZenControl site representing a physical building or location."""

    model_config = ConfigDict(populate_by_name=True)

    site_id: str | None = Field(default=None, alias="siteId")
    tag: str | None = None
    name: str | None = None
    udp_enabled: bool | None = Field(default=None, alias="udpEnabled")
    building_size: float | None = Field(default=None, alias="buildingSize")
    address: Address | None = None
    geographic_location: GeographicLocation | None = Field(
        default=None, alias="geographicLocation"
    )


class Floor(BaseModel):
    """A floor within a site."""

    model_config = ConfigDict(populate_by_name=True)

    floor_id: str | None = Field(default=None, alias="floorId")
    label: str | None = None
    site_id: str | None = Field(default=None, alias="siteId")


class Map(BaseModel):
    """A map associated with a floor or tenancy."""

    model_config = ConfigDict(populate_by_name=True)

    map_id: str | None = Field(default=None, alias="mapId")
    floor_id: str | None = Field(default=None, alias="floorId")
    tenancy_id: str | None = Field(default=None, alias="tenancyId")
    label: StringField | None = None
    default: bool | None = None
    status: StatusField | None = None


class Tenancy(BaseModel):
    """A tenancy within a site, used for logical grouping of areas."""

    model_config = ConfigDict(populate_by_name=True)

    tenancy_id: str | None = Field(default=None, alias="tenancyId")
    site_id: str | None = Field(default=None, alias="siteId")
    label: str | None = None
    status: StatusField | None = None


class Zone(BaseModel):
    """A zone within a control system."""

    model_config = ConfigDict(populate_by_name=True)

    zone_id: str | None = Field(default=None, alias="zoneId")
    label: StringField | None = None
    ip_address: StringField | None = Field(default=None, alias="ipAddress")
    status: StatusField | None = None


class GroupVisibility(BaseModel):
    """Visibility settings for a DALI group."""

    model_config = ConfigDict(populate_by_name=True)

    plan_view: bool | None = Field(default=None, alias="planView")
    user: bool | None = None


class Group(BaseModel):
    """A DALI group within a control system.

    Groups are collections of lighting devices that can be controlled
    together. Each group has a composite ID (gateway + group number 0-15).
    """

    model_config = ConfigDict(populate_by_name=True)

    group_id: GroupId | None = Field(default=None, alias="groupId")
    type: GroupTypeField | None = None
    label: StringField | None = None
    status: StatusField | None = None
    map_id: str | None = Field(default=None, alias="mapId")
    visibility: GroupVisibility | None = None


class Gateway(BaseModel):
    """A ZenControl gateway that bridges DALI bus devices to the cloud.

    In URL paths, gateways are identified as ``{gtin}-{serial}``.
    """

    model_config = ConfigDict(populate_by_name=True)

    gateway_id: DaliId | None = Field(default=None, alias="gatewayId")
    control_system_id: str | None = Field(default=None, alias="controlSystemId")
    label: StringField | None = None
    identifier: IntField | None = None
    firmware_version: str | None = Field(default=None, alias="firmwareVersion")
    sync_status: dict | None = Field(default=None, alias="syncStatus")
    mac_address: str | None = Field(default=None, alias="macAddress")


class ControlSystem(BaseModel):
    """A control system managing gateways and devices within a site."""

    model_config = ConfigDict(populate_by_name=True)

    control_system_id: str | None = Field(default=None, alias="controlSystemId")
    site_id: str | None = Field(default=None, alias="siteId")
    tenancy_id: str | None = Field(default=None, alias="tenancyId")
    label: StringField | None = None
    identifier: IntField | None = None
    gateways: list[Gateway] | None = None
    profiles: list[dict] | None = None


class DeviceEcg(BaseModel):
    """An ECG (Emergency Control Gear) component within a device."""

    model_config = ConfigDict(populate_by_name=True)

    ecg_id: EcgId | None = Field(default=None, alias="ecgId")
    label: StringField | None = None
    status: StatusField | None = None


class DeviceEcd(BaseModel):
    """An ECD (Emergency Control Device) component within a device."""

    model_config = ConfigDict(populate_by_name=True)

    ecd_id: EcgId | None = Field(default=None, alias="ecdId")
    label: StringField | None = None
    status: StatusField | None = None


class Device(BaseModel):
    """A DALI bus device (luminaire, sensor, etc.) on a gateway."""

    model_config = ConfigDict(populate_by_name=True)

    device_id: DeviceId | None = Field(default=None, alias="deviceId")
    device_location_id: str | None = Field(default=None, alias="deviceLocationId")
    label: StringField | None = None
    identifier: IntField | None = None
    status: StatusField | None = None
    ecgs: list[DeviceEcg] | None = None
    ecds: list[DeviceEcd] | None = None


class DeviceLocation(BaseModel):
    """A logical device location within a control system.

    Represents a slot that a physical device can be assigned to.
    """

    model_config = ConfigDict(populate_by_name=True)

    device_location_id: str | None = Field(default=None, alias="deviceLocationId")
    control_system_id: str | None = Field(default=None, alias="controlSystemId")
    label: StringField | None = None
    identifier: IntField | None = None
    status: StatusField | None = None
    device_id: DeviceId | None = Field(default=None, alias="deviceId")


class SceneField(BaseModel):
    """Scene configuration for a DALI group or device."""

    model_config = ConfigDict(populate_by_name=True)

    level: IntField | None = None
    colour_temperature: IntField | None = Field(default=None, alias="colourTemperature")


class Ecg(BaseModel):
    """Emergency Control Gear — a controllable lighting component.

    Represents an individually addressable gear on the DALI bus such as
    an LED driver or ballast.
    """

    model_config = ConfigDict(populate_by_name=True)

    ecg_id: EcgId | None = Field(default=None, alias="ecgId")
    label: StringField | None = None
    identifier: IntField | None = None
    address: IntField | None = None
    status: StatusField | None = None
    device_type: dict | None = Field(default=None, alias="deviceType")
    groups: list[dict] | None = None
    operating_mode: IntField | None = Field(default=None, alias="operatingMode")


class Ecd(BaseModel):
    """Emergency Control Device — an input/sensor component.

    Represents an individually addressable control device on the DALI bus
    such as a sensor or switch.
    """

    model_config = ConfigDict(populate_by_name=True)

    ecd_id: EcgId | None = Field(default=None, alias="ecdId")
    label: StringField | None = None
    identifier: IntField | None = None
    address: IntField | None = None
    status: StatusField | None = None
    device_type: dict | None = Field(default=None, alias="deviceType")
    groups: list[dict] | None = None
    operating_mode: IntField | None = Field(default=None, alias="operatingMode")


class Profile(BaseModel):
    """Lighting profile (e.g., 'Work hours', 'After hours')."""

    model_config = ConfigDict(populate_by_name=True)

    profile_id: str | None = Field(None, alias="profileId")
    site_id: str | None = Field(None, alias="siteId")
    label: StringField | None = None
    profile_number: IntField | None = Field(None, alias="profileNumber")
    status: StatusField | None = None


class Scene(BaseModel):
    """DALI scene configuration."""

    model_config = ConfigDict(populate_by_name=True)

    scene_id: str | None = Field(None, alias="sceneId")
    label: str | None = None
    scene_number: int | None = Field(None, alias="sceneNumber")


# ---------------------------------------------------------------------------
# DALI command models
# ---------------------------------------------------------------------------


class OverrideType(BaseModel):
    """Override flags for the ``overrideTarget`` DALI command."""

    model_config = ConfigDict(populate_by_name=True)

    lux: bool | None = None
    pir: bool | None = None
    colour: bool | None = None
    intensity: bool | None = None
    switch: bool | None = None
    inhibit_without_switch: bool | None = Field(
        default=None, alias="inhibitWithoutSwitch"
    )
    inhibit_with_switch: bool | None = Field(default=None, alias="inhibitWithSwitch")


class DaliCommand(BaseModel):
    """A DALI command payload to send to a target.

    Different command types use different subsets of the optional fields.
    For example, ``setLevel`` uses *level*, ``goToScene`` uses *scene*,
    and ``colourTemperature`` uses *temperature* (in mirek).
    """

    model_config = ConfigDict(populate_by_name=True)

    type: DaliCommandType
    level: int | None = Field(default=None, ge=0, le=255)
    fast_fade: bool | None = Field(default=None, alias="fastFade")
    scene: int | None = Field(default=None, ge=0, le=15)
    profile_number: int | None = Field(
        default=None, alias="profileNumber", ge=0, le=65535
    )
    temperature: int | None = Field(default=None, ge=0, le=65534)
    x: int | None = None
    y: int | None = None
    control: int | None = None
    rgbwaf: list[int] | None = Field(default=None, min_length=6, max_length=6)
    override_type: OverrideType | None = Field(default=None, alias="overrideType")
    override_time: int | None = Field(default=None, alias="overrideTime")


class DaliCommandError(BaseModel):
    """A single error from a DALI command execution."""

    model_config = ConfigDict(populate_by_name=True)

    error_code: int = Field(alias="errorCode")
    error_message: str = Field(alias="errorMessage")


class DaliCommandErrors(BaseModel):
    """Collection of errors returned from a DALI command execution."""

    model_config = ConfigDict(populate_by_name=True)

    errors: list[DaliCommandError] = Field(default_factory=list)
