from typing import Optional
from appdaemon.adapi import Entity
import hassapi as hass
from datetime import datetime
from appdaemon import adbase as ad


class Light(hass.Hass, ad.ADBase):
    sensor_occupancy_entity: Entity
    sensor_illuminance_entity: Entity | None = None
    light_entity: Entity
    illuminance_threshold: int = 10
    night_mode_entity: Entity
    disabled_entity: Optional[str] = None

    day_illuminance: int = 255
    night_illuminance: int = 10

    expected_action = None

    def initialize(self) -> None:
        self.adapi = self.get_ad_api()
        self.init_values()
        self.init_listeners()

        self.update_light_state()

    def init_values(self) -> None:
        self.sensor_occupancy_entity = self.adapi.get_entity(
            self.args["sensor_occupancy"]
        )
        if "sensor_illuminance" in self.args:
            self.sensor_illuminance_entity = self.adapi.get_entity(
                self.args["sensor_illuminance"]
            )
        self.light_entity = self.adapi.get_entity(self.args["light"])
        self.illuminance_threshold = int(self.args["illuminance_threshold"])
        self.night_mode_entity = self.adapi.get_entity(self.args["night_mode"])
        self.day_illuminance = self.args["day_illuminance"]
        self.night_illuminance = self.args["night_illuminance"]
        self.manual_mode_debounce = int(self.args.get("manual_mode_debounce", 180))
        self.disabled_entity = self.args.get("disabled")

        self.manual_action_registered_on = None

    def init_listeners(self) -> None:
        self.sensor_occupancy_entity.listen_state(self.update_light_state_listener)
        if self.sensor_illuminance_entity:
            self.sensor_illuminance_entity.listen_state(
                self.update_light_state_listener
            )
        self.night_mode_entity.listen_state(self.update_light_state_listener)
        self.light_entity.listen_state(self.handle_light_change)

    def is_disabled(self) -> bool:
        if not self.disabled_entity:
            return False
        return self.get_state(self.disabled_entity) == "on"

    def handle_light_change(self, _entity, _attribute, _old, new, *kwargs) -> None:
        if new == self.expected_action:
            self.expected_action = None
            return
        self.manual_action_registered_on = datetime.now()
        self.adapi.log(
            f"manual action registered on { self.manual_action_registered_on }"
        )
        self.adapi.run_in(self.update_light_state, self.manual_mode_debounce)

    def get_illuminance(self) -> int:
        assert self.sensor_illuminance_entity is not None
        return self.sensor_illuminance_entity.get_state()

    def get_occupancy(self) -> bool:
        return self.sensor_occupancy_entity.get_state() == "on"

    def is_night_mode(self) -> bool:
        # return self.get_state(self.night_mode_entity) == "on"
        return self.night_mode_entity.get_state() == "on"

    def light_is_on(self) -> bool:
        # return self.get_state(self.light_entity) == "on"
        return self.light_entity.get_state() == "on"

    def calculate_light_state(self) -> bool:
        if self.is_disabled():
            self.adapi.log("light is disabled")
            return False
        if not self.get_occupancy():
            self.adapi.log("no occupancy")
            return False
        if self.light_is_on():
            self.adapi.log("light is already on")
            return True

        if self.sensor_illuminance_entity is None:
            return True

        if self.get_illuminance() < self.illuminance_threshold:
            self.adapi.log("too dark - light should be on")
            return True
        self.adapi.log("bright enough - light should be off")
        return False

    def calculate_light_brightness(self) -> int:
        if self.is_night_mode():
            return self.night_illuminance
        return self.day_illuminance

    def get_brightness(self, entity: Entity) -> int:
        return entity.get_state(attribute="brightness")

    def update_needed(self, new_light_state) -> bool:
        if (
            self.manual_action_registered_on
            and (datetime.now() - self.manual_action_registered_on).total_seconds()
            < self.manual_mode_debounce
        ):
            return False

        if new_light_state != self.light_is_on():
            return True

        if not self.light_is_on():
            return False

        if not self.day_illuminance or not self.night_illuminance:
            return False

        desired_brightess = self.calculate_light_brightness()
        return desired_brightess != self.get_brightness(self.light_entity)

    def update_light_state_listener(
        self, _entity, _attribute, _old, _new, *args, **kwargs
    ) -> None:
        self.update_light_state()

    def update_light_state(self) -> None:
        should_light_on = self.calculate_light_state()
        self.adapi.log(f"light should be {should_light_on and 'on' or 'off'}")
        if not self.update_needed(should_light_on):
            return

        self.adapi.log(f"light is set to {should_light_on and 'on' or 'off'}")

        self.expected_action = should_light_on and "on" or "off"

        if should_light_on:
            kwargs = {}
            kwargs["brightness"] = self.calculate_light_brightness()
            self.light_entity.turn_on(**kwargs)
            return

        self.light_entity.turn_off()
