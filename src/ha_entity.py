from typing import Callable

from ha_core import DeviceClass, StateClass, device_class_serialized, state_class_serialized


class HaEntity:
    def __init__(
            self,
            component_id: str,
            name: str,
            device_class: DeviceClass,
            state_class: StateClass,
            unit: str,
            lookup: Callable[[], str | int | float | None],
            suggested_display_precision: int | None = None,
            icon: str | None = None,
            entity_category: str | None = None,
            availability_topic: str | None = None,
    ):
        self.component_id = component_id
        self.name = name
        self.device_class = device_class
        self.state_class = state_class
        self.unit = unit
        self.lookup = lookup
        self.suggested_display_precision = suggested_display_precision
        self.icon = icon
        self.entity_category = entity_category
        self.availability_topic = availability_topic

    def state_topic(self, device_id: str, discovery_prefix: str):
        return f"{discovery_prefix}/sensor/{device_id}/{self.component_id}/state"

    def get_discovery_config(self, device_id: str, discovery_prefix: str):
        config = {
            "platform": "sensor",
            "name": self.name,
            "unique_id": f"{device_id}_{self.component_id}",
            "state_topic": self.state_topic(device_id, discovery_prefix),
        }

        device_class = device_class_serialized(self.device_class)
        if device_class:
            config["device_class"] = device_class

        state_class = state_class_serialized(self.state_class)
        if state_class:
            config["state_class"] = state_class

        if self.unit:
            config["unit_of_measurement"] = self.unit

        if self.suggested_display_precision is not None:
            config["suggested_display_precision"] = self.suggested_display_precision

        if self.icon:
            config["icon"] = self.icon

        if self.entity_category:
            config["entity_category"] = self.entity_category

        if self.availability_topic:
            config["availability_topic"] = self.availability_topic
            config["payload_available"] = "online"
            config["payload_not_available"] = "offline"

        return config
