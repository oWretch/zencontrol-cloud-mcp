"""Tests for Pydantic model validation."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from zencontrol_mcp.models.schemas import (
    CommandTargetType,
    DaliCommand,
    DaliCommandType,
    Device,
    DeviceId,
    Group,
    GroupId,
    IntField,
    ScopeType,
    Site,
    StatusField,
    StringField,
    Tenancy,
)


# ---------------------------------------------------------------------------
# Site model
# ---------------------------------------------------------------------------


class TestSiteModel:
    def test_site_from_api_data(self, sample_site):
        site = Site.model_validate(sample_site)
        assert site.site_id == "3b5b2c02-0e43-423f-9719-758ab3fcb456"
        assert site.tag == "hq"
        assert site.name == "HQ Office"
        assert site.building_size == 350.1

    def test_site_address(self, sample_site):
        site = Site.model_validate(sample_site)
        assert site.address is not None
        assert site.address.country == "AU"
        assert site.address.admin_area == "QLD"
        assert site.address.locality == "Brisbane"
        assert site.address.post_code == "4000"
        assert site.address.street == "123 Main St"

    def test_site_geographic_location(self, sample_site):
        site = Site.model_validate(sample_site)
        assert site.geographic_location is not None
        assert site.geographic_location.latitude == pytest.approx(-27.47)
        assert site.geographic_location.longitude == pytest.approx(153.02)

    def test_site_minimal(self):
        """A site with only a name should validate."""
        site = Site.model_validate({"name": "Minimal Site"})
        assert site.name == "Minimal Site"
        assert site.site_id is None
        assert site.address is None

    def test_site_empty(self):
        """An empty dict is valid since all fields are optional."""
        site = Site.model_validate({})
        assert site.name is None


# ---------------------------------------------------------------------------
# Group model
# ---------------------------------------------------------------------------


class TestGroupModel:
    def test_group_from_api_data(self, sample_group):
        group = Group.model_validate(sample_group)
        assert group.group_id is not None
        assert group.group_id.group_number == 5
        assert group.group_id.gateway_id.gtin == 565343546
        assert group.group_id.gateway_id.serial == "AABBCCDD"

    def test_group_label(self, sample_group):
        group = Group.model_validate(sample_group)
        assert group.label is not None
        assert group.label.value == "Office 3.02"
        assert group.label.state == "OK"

    def test_group_type_field(self, sample_group):
        group = Group.model_validate(sample_group)
        assert group.type is not None
        assert group.type.value == "STANDARD"

    def test_group_status(self, sample_group):
        group = Group.model_validate(sample_group)
        assert group.status is not None
        assert group.status.value == "ACTIVE"

    def test_group_id_validation(self):
        """GroupId enforces groupNumber 0-15."""
        GroupId.model_validate(
            {"gatewayId": {"gtin": 1, "serial": "A"}, "groupNumber": 0}
        )
        GroupId.model_validate(
            {"gatewayId": {"gtin": 1, "serial": "A"}, "groupNumber": 15}
        )
        with pytest.raises(ValidationError):
            GroupId.model_validate(
                {"gatewayId": {"gtin": 1, "serial": "A"}, "groupNumber": 16}
            )
        with pytest.raises(ValidationError):
            GroupId.model_validate(
                {"gatewayId": {"gtin": 1, "serial": "A"}, "groupNumber": -1}
            )


# ---------------------------------------------------------------------------
# Device model
# ---------------------------------------------------------------------------


class TestDeviceModel:
    def test_device_from_api_data(self, sample_device):
        device = Device.model_validate(sample_device)
        assert device.device_id is not None
        assert device.device_id.gateway_id.gtin == 565343546
        assert device.device_id.bus_unit_id.serial == "11223344"

    def test_device_location_id(self, sample_device):
        device = Device.model_validate(sample_device)
        assert device.device_location_id == "758ab3fc-423f-0e43-9719-b4563b5b2c02"

    def test_device_label_and_status(self, sample_device):
        device = Device.model_validate(sample_device)
        assert device.label is not None
        assert device.label.value == "End of hallway"
        assert device.status is not None
        assert device.status.value == "ACTIVE"

    def test_device_id_structure(self):
        """DeviceId requires nested gatewayId and busUnitId."""
        did = DeviceId.model_validate(
            {
                "gatewayId": {"gtin": 100, "serial": "GW01"},
                "busUnitId": {"gtin": 200, "serial": "BU01"},
            }
        )
        assert did.gateway_id.gtin == 100
        assert did.bus_unit_id.serial == "BU01"


# ---------------------------------------------------------------------------
# DaliCommand model
# ---------------------------------------------------------------------------


class TestDaliCommandModel:
    def test_set_level_command(self):
        cmd = DaliCommand(type=DaliCommandType.SET_LEVEL, level=200)
        assert cmd.type == DaliCommandType.SET_LEVEL
        assert cmd.level == 200

    def test_go_to_scene_command(self):
        cmd = DaliCommand(type=DaliCommandType.GO_TO_SCENE, scene=10)
        assert cmd.type == DaliCommandType.GO_TO_SCENE
        assert cmd.scene == 10

    def test_colour_temperature_command(self):
        cmd = DaliCommand(type=DaliCommandType.COLOUR_TEMPERATURE, temperature=250)
        assert cmd.type == DaliCommandType.COLOUR_TEMPERATURE
        assert cmd.temperature == 250

    def test_level_validation_range(self):
        """level must be 0-255."""
        DaliCommand(type=DaliCommandType.SET_LEVEL, level=0)
        DaliCommand(type=DaliCommandType.SET_LEVEL, level=255)
        with pytest.raises(ValidationError):
            DaliCommand(type=DaliCommandType.SET_LEVEL, level=256)
        with pytest.raises(ValidationError):
            DaliCommand(type=DaliCommandType.SET_LEVEL, level=-1)

    def test_scene_validation_range(self):
        """scene must be 0-15."""
        DaliCommand(type=DaliCommandType.GO_TO_SCENE, scene=0)
        DaliCommand(type=DaliCommandType.GO_TO_SCENE, scene=15)
        with pytest.raises(ValidationError):
            DaliCommand(type=DaliCommandType.GO_TO_SCENE, scene=16)
        with pytest.raises(ValidationError):
            DaliCommand(type=DaliCommandType.GO_TO_SCENE, scene=-1)

    def test_off_command(self):
        cmd = DaliCommand(type=DaliCommandType.OFF)
        assert cmd.type == DaliCommandType.OFF
        assert cmd.level is None

    def test_rgbwaf_command(self):
        cmd = DaliCommand(
            type=DaliCommandType.COLOUR_RGBWAF,
            rgbwaf=[100, 150, 200, 255, 255, 255],
        )
        assert cmd.rgbwaf == [100, 150, 200, 255, 255, 255]

    def test_rgbwaf_length_validation(self):
        """rgbwaf must have exactly 6 elements."""
        with pytest.raises(ValidationError):
            DaliCommand(
                type=DaliCommandType.COLOUR_RGBWAF,
                rgbwaf=[100, 150, 200],
            )
        with pytest.raises(ValidationError):
            DaliCommand(
                type=DaliCommandType.COLOUR_RGBWAF,
                rgbwaf=[1, 2, 3, 4, 5, 6, 7],
            )

    def test_serialization_by_alias(self):
        cmd = DaliCommand(
            type=DaliCommandType.SET_LEVEL,
            level=127,
            fast_fade=True,
        )
        data = cmd.model_dump(by_alias=True)
        assert data["fastFade"] is True
        assert data["type"] == "setLevel"


# ---------------------------------------------------------------------------
# Field types
# ---------------------------------------------------------------------------


class TestFieldTypes:
    def test_string_field(self):
        sf = StringField(value="hello", state="OK", error=None)
        assert sf.value == "hello"
        assert sf.state == "OK"
        assert sf.error is None

    def test_string_field_empty(self):
        sf = StringField()
        assert sf.value is None

    def test_string_field_from_plain_string(self):
        sf = StringField.model_validate("Office")
        assert sf.value == "Office"
        assert sf.state is None
        assert sf.error is None

    def test_tenancy_label_from_plain_string(self):
        tenancy = Tenancy.model_validate(
            {
                "tenancyId": "tenancy-1",
                "siteId": "site-1",
                "label": "Office",
            }
        )
        assert tenancy.label is not None
        assert tenancy.label.value == "Office"

    def test_int_field(self):
        intf = IntField(value=42, state="OK", error=None)
        assert intf.value == 42

    def test_int_field_empty(self):
        intf = IntField()
        assert intf.value is None

    def test_status_field_active(self):
        sf = StatusField(value="ACTIVE", state="OK")
        assert sf.value == "ACTIVE"

    def test_status_field_inactive(self):
        sf = StatusField(value="INACTIVE")
        assert sf.value == "INACTIVE"

    def test_status_field_invalid(self):
        with pytest.raises(ValidationError):
            StatusField(value="BROKEN")


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------


class TestEnums:
    def test_scope_type_values(self):
        assert ScopeType.SITE == "site"
        assert ScopeType.FLOOR == "floor"
        assert ScopeType.GATEWAY == "gateway"
        assert ScopeType.ZONE == "zone"
        assert ScopeType.MAP == "map"
        assert ScopeType.TENANCY == "tenancy"
        assert ScopeType.CONTROL_SYSTEM == "control_system"

    def test_command_target_type_values(self):
        assert CommandTargetType.GROUP == "group"
        assert CommandTargetType.DEVICE == "device"
        assert CommandTargetType.ECG == "ecg"
        assert CommandTargetType.ECD == "ecd"
        assert CommandTargetType.DEVICE_LOCATION == "device_location"

    def test_dali_command_type_values(self):
        assert DaliCommandType.OFF == "off"
        assert DaliCommandType.RECALL_MAX == "recallMax"
        assert DaliCommandType.SET_LEVEL == "setLevel"
        assert DaliCommandType.GO_TO_SCENE == "goToScene"
        assert DaliCommandType.COLOUR_TEMPERATURE == "colourTemperature"
        assert DaliCommandType.COLOUR_RGBWAF == "colourRgbwaf"
        assert DaliCommandType.IDENTIFY == "identify"
        assert DaliCommandType.STEP_UP == "stepUp"
        assert DaliCommandType.STEP_DOWN == "stepDown"
        assert DaliCommandType.DIM_UP == "dimUp"
        assert DaliCommandType.DIM_DOWN == "dimDown"
