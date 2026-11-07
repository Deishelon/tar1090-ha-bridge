from enum import Enum


# https://www.home-assistant.io/integrations/sensor/#device-class
class DeviceClass(Enum):
    NONE = 0
    DURATION = 1
    DISTANCE = 2


def device_class_serialized(device: DeviceClass) -> str | None:
    match device:
        case DeviceClass.NONE:
            return None
        case DeviceClass.DURATION:
            return "duration"
        case DeviceClass.DISTANCE:
            return "distance"


class StateClass(Enum):
    NONE = 0
    measurement = 1
    total_increasing = 2


def state_class_serialized(state: StateClass) -> str | None:
    match state:
        case StateClass.NONE:
            return None
        case StateClass.measurement:
            return "measurement"
        case StateClass.total_increasing:
            return "total_increasing"
