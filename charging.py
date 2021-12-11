from typing import Dict
from mogottsch.notification import UseNotifier
import hassapi as hass
from datetime import datetime


class PhoneCharger(UseNotifier):
    CHARGING_THRESHOLD = 80
    devices: Dict[str, Dict[str, str]] = []
    charger_entity: str = None
    detected_device_entity: str = None

    charger_turned_on: datetime = None
    detected_device: Dict = None
    temp_listeners: list = []

    def initialize(self) -> None:
        super().initialize()
        self.init_values()
        self.init_listeners()

    def init_values(self) -> None:
        self.devices = self.args["devices"]
        self.charger_entity = self.args["charger"]
        self.detected_device_entity = self.args["detected_device"]

    def init_listeners(self) -> None:
        self.listen_state(self.handle_charger_turned_on,
                          self.charger_entity,
                          new="on")
        for key, device in self.devices.items():
            self.listen_state(self.handle_charging_started,
                              device['charging'],
                              new="on",
                              duration=15)

    def handle_charging_started(self, entity, attribute, old, new,
                                kwargs) -> None:

        if self.charger_turned_on is None or \
                (datetime.now() - self.charger_turned_on).seconds > 60:
            self.log(
                "Device started charging but charger not turned on recently")
            return
        self.set_detected_device(entity)

    def handle_charger_turned_on(self, entity, attribute, old, new,
                                 kwargs) -> None:
        self.charger_turned_on = datetime.now()
        self.log("Charger turned on")

    def handle_charger_turned_off(self, entity, attribute, old, new,
                                  kwargs) -> None:
        self.log("Charger turned off")
        self.stop_charging()

    def set_detected_device(self, charging_entity: str) -> None:
        detected_device = [
            device for device in self.devices.values()
            if device['charging'] == charging_entity
        ][0]
        self.log(f"Detected device: {detected_device['name']}")
        self.detected_device = detected_device
        self.set_detected_device_input(detected_device['name'])

        handle_battery = self.listen_state(
            self.handle_battery_threshold_reached,
            detected_device['battery_level'])
        handle_stop = self.listen_state(self.handle_charging_stopped,
                                        detected_device['charging'],
                                        new="off")
        self.temp_listeners.append(handle_battery)
        self.temp_listeners.append(handle_stop)

        self.notify(f"Ladevorgang für {detected_device['name']} gestartet")

    def handle_battery_threshold_reached(self, entity, attribute, old, new,
                                         kwargs) -> bool:
        if int(new) < self.CHARGING_THRESHOLD:
            self.log(
                f"Battery level {new} is below threshold {self.CHARGING_THRESHOLD}"
            )
            return

        self.notify(
            f"Ladevorgang für {self.detected_device['name']} abgeschlossen")
        self.log(f"Battery level reached for {self.detected_device['name']}")
        self.stop_charging()

    def handle_charging_stopped(self, entity, attribute, old, new,
                                kwargs) -> None:
        self.log(f"Charging stopped for {self.detected_device['name']}")
        self.stop_charging()

    def stop_charging(self) -> None:
        self.turn_off_charger()
        self.clear_detected_device()
        self.flush_temp_listeners()

    def flush_temp_listeners(self) -> None:
        for listener in self.temp_listeners:
            self.cancel_listen_event(listener)
        self.temp_listeners = []

    def clear_detected_device(self) -> None:
        self.detected_device = None
        self.set_detected_device_input("")

    def turn_off_charger(self) -> None:
        self.turn_off(self.charger_entity)

    def set_detected_device_input(self, device_name: str) -> None:
        self.call_service("input_text/set_value",
                          entity_id=self.detected_device_entity,
                          value=device_name)
