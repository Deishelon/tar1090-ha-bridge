from abc import ABC, abstractmethod


class MqttClientInterface(ABC):
    @abstractmethod
    def publish(self, topic: str, payload: str, retain: bool):
        """
        Publishes a message to the MQTT topic.
        :param topic: The MQTT topic to publish to.
        :param payload: The message payload.
        :param retain: Whether the message should be retained by the broker.
        """
        pass
