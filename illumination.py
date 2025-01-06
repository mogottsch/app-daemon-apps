from appdaemon.adapi import Entity
import hassapi as hass
from datetime import datetime
from appdaemon import adbase as ad


class BathroomCeilingLight(hass.Hass, ad.ADBase):
    sensor_occupancy_entity: Entity
    light_entity: Entity
    night_mode_entity: Entity
    chill_mode_entity: Entity
    disabled_entity: Entity | None = None
    day_illuminance: int
    night_illuminance: int
    normal_temeparture: int
    chill_temperature: int

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
        self.light_entity = self.adapi.get_entity(self.args["light"])
        self.night_mode_entity = self.adapi.get_entity(self.args["night_mode"])
        self.chill_mode_entity = self.adapi.get_entity(self.args["chill_mode"])
        self.day_illuminance = self.args["day_illuminance"]
        self.night_illuminance = self.args["night_illuminance"]
        self.normal_temperature = self.args.get("normal_temperature")
        self.chill_temperature = self.args.get("chill_temperature")
        self.manual_mode_debounce = int(self.args.get("manual_mode_debounce", 180))
        if "disabled" in self.args:
            self.disabled_entity = self.adapi.get_entity(self.args["disabled"])

        self.has_temperature = (
            self.normal_temperature is not None and self.chill_temperature is not None
        )
        self.has_illuminance = (
            self.day_illuminance is not None and self.night_illuminance is not None
        )

        self.manual_action_registered_on = None

    def init_listeners(self) -> None:
        self.sensor_occupancy_entity.listen_state(self.update_light_state)
        self.night_mode_entity.listen_state(self.update_light_state)
        self.chill_mode_entity.listen_state(self.update_light_state)
        self.light_entity.listen_state(self.handle_light_change)

    def is_disabled(self) -> bool:
        if not self.disabled_entity:
            return False
        return self.disabled_entity.get_state() == "on"

    def handle_light_change(self, entity, attribute, old, new, *kwargs) -> None:
        if new == self.expected_action:
            self.expected_action = None
            return
        self.manual_action_registered_on = datetime.now()
        self.adapi.log(
            f"manual action registered on {self.manual_action_registered_on}"
        )
        self.adapi.run_in(self.update_light_state, self.manual_mode_debounce)

    def get_occupancy(self) -> bool:
        return self.sensor_occupancy_entity.get_state() == "on"

    def is_night_mode(self) -> bool:
        return self.night_mode_entity.get_state() == "on"

    def is_chill_mode(self) -> bool:
        return self.chill_mode_entity.get_state() == "on"

    def light_is_on(self) -> bool:
        return self.light_entity.get_state() == "on"

    def calculate_light_state(self) -> bool:
        if self.is_disabled():
            self.adapi.log("light is disabled")
            return False
        if not self.get_occupancy():
            self.adapi.log("no occupancy")
            return False
        return True

    def calculate_light_brightness(self) -> int:
        if self.is_night_mode():
            return self.night_illuminance
        return self.day_illuminance

    def calculate_light_temperature(self) -> int:
        if self.is_chill_mode():
            return self.chill_temperature
        return self.normal_temperature

    def get_brightness(self, entity: Entity) -> int:
        return int(entity.get_state(attribute="brightness"))

    def get_temperature(self, entity: Entity) -> int:
        return int(entity.get_state(attribute="color_temp"))

    def update_needed(self, new_light_state: bool) -> bool:
        if (
            self.manual_action_registered_on
            and (datetime.now() - self.manual_action_registered_on).total_seconds()
            < self.manual_mode_debounce
        ):
            self.adapi.log("recent manual action - no update needed")
            return False

        if new_light_state != self.light_is_on():
            self.adapi.log("light state mismatch - update needed")
            return True

        if not self.light_is_on():
            self.adapi.log("light is off - no need to check for brightness")
            return False

        if self.has_illuminance:
            desired_brightess = self.calculate_light_brightness()
            if desired_brightess != self.get_brightness(self.light_entity):
                self.adapi.log("brightness mismatch - update needed")
                return True

        if self.has_temperature:
            desired_temperature = self.calculate_light_temperature()
            if desired_temperature != self.get_temperature(self.light_entity):
                self.adapi.log("temperature mismatch - update needed")
                return True
        return False

    def update_light_state(self, *_) -> None:
        should_light_on = self.calculate_light_state()
        self.adapi.log(f"light should be {should_light_on and 'on' or 'off'}")
        if not self.update_needed(should_light_on):
            self.adapi.log("no update needed")
            return

        self.adapi.log(f"light is set to {should_light_on and 'on' or 'off'}")

        self.expected_action = should_light_on and "on" or "off"

        if should_light_on:
            kwargs = {}
            kwargs["brightness"] = self.calculate_light_brightness()
            if self.has_temperature:
                kwargs["color_temp"] = self.calculate_light_temperature()
            # self.adapi.log(
            #     f"setting light on with brightness {kwargs['brightness']} and temperature {kwargs['color_temp']}"
            # )
            self.light_entity.turn_on(**kwargs)
            return

        self.light_entity.turn_off()
