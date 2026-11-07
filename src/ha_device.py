from typing import List

from ha_entity import HaEntity


class HaDevice:
    def __init__(
            self,
            device_id: str,
            device_name: str,
            model: str,
            manufacturer: str,
            origin_name: str = "tar1090-ha-bridge",
            sw_version: str = "1.0",
            support_url: str = "https://github.com/Deishelon/tar1090-ha-bridge",
    ):
        self.device_id = device_id
        self.device_name = device_name
        self.model = model
        self.manufacturer = manufacturer
        self.origin_name = origin_name
        self.sw_version = sw_version
        self.support_url = support_url
        self.entities: List[HaEntity] = []

    def set_entities(self, entities: List[HaEntity]):
        self.entities = list(entities)

    def get_discovery(self, discovery_prefix: str):
        payload = {
            "device": {
                "identifiers": [self.device_id],
                "name": self.device_name,
                "manufacturer": self.manufacturer,
                "model": self.model,
            },
            "origin": {
                "name": self.origin_name,
                "sw_version": self.sw_version,
                "support_url": self.support_url,
            },
            "components": {
                entity.component_id: entity.get_discovery_config(self.device_id, discovery_prefix)
                for entity in self.entities
            },
            "qos": 1,
        }
        topic = f"{discovery_prefix}/device/{self.device_id}/config"
        return topic, payload
