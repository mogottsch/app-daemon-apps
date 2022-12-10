import hassapi as hass
from datetime import datetime


class Light(hass.Hass):
    sensor_occupancy_entity: str = None
    sensor_illuminance_entity: str = None
    light_entity: str = None
    illuminance_threshold: int = None
    night_mode_entity: str = None

    day_illuminance: int = None
    night_illuminance: int = None

    expected_action = None

    def initialize(self) -> None:
        self.init_values()
        self.init_listeners()

        self.update_light_state()

    def init_values(self) -> None:
        self.sensor_occupancy_entity = self.args["sensor_occupancy"]
        self.sensor_illuminance_entity = self.args["sensor_illuminance"]
        self.light_entity = self.args["light"]
        self.illuminance_threshold = int(self.args.get("illuminance_threshold", 10))
        self.night_mode_entity = self.args["night_mode"]
        self.day_illuminance = self.args.get("day_illuminance")
        self.night_illuminance = self.args.get("night_illuminance")
        self.manual_mode_debounce = int(self.args.get("manual_mode_debounce", 180))

        self.manual_action_registered_on = None

    def init_listeners(self) -> None:
        self.listen_state(self.update_light_state, self.sensor_occupancy_entity)
        self.listen_state(self.update_light_state, self.sensor_illuminance_entity)
        self.listen_state(self.update_light_state, self.night_mode_entity)
        self.listen_state(self.handle_light_change, self.light_entity)

    def handle_light_change(self, entity, attribute, old, new, *kwargs) -> None:
        if new == self.expected_action:
            self.expected_action = None
            return
        self.manual_action_registered_on = datetime.now()
        self.log(f"manual action registered on {self.manual_action_registered_on}")
        self.run_in(self.update_light_state, self.manual_mode_debounce)

    def get_illuminance(self) -> int:
        return int(self.get_state(self.sensor_illuminance_entity))

    def get_occupancy(self) -> bool:
        return self.get_state(self.sensor_occupancy_entity) == "on"

    def is_night_mode(self) -> bool:
        return self.get_state(self.night_mode_entity) == "on"

    def light_is_on(self) -> bool:
        return self.get_state(self.light_entity) == "on"

    def calculate_light_state(self) -> bool:
        if not self.get_occupancy():
            return False
        if self.light_is_on():
            return True
        if self.get_illuminance() < self.illuminance_threshold:
            return True
        return False

    def calculate_light_brightness(self) -> int:
        if self.is_night_mode():
            return self.night_illuminance
        return self.day_illuminance

    def get_brightness(self, entity_id) -> int:
        return int(self.get_state(entity_id, attribute="brightness"))

    def update_needed(self, new_light_state) -> bool:
        if (
            self.manual_action_registered_on
            and (datetime.now() - self.manual_action_registered_on).total_seconds()
            < self.manual_mode_debounce
        ):
            return False

        if new_light_state != self.light_is_on():
            return True

        # further check if brightness adjustment is needed

        if not self.light_is_on():
            return False

        if not self.day_illuminance or not self.night_illuminance:
            return False

        desired_brightess = self.calculate_light_brightness()
        return desired_brightess != self.get_brightness(self.light_entity)

    def update_light_state(self, *_) -> None:
        new_light_state = self.calculate_light_state()
        if not self.update_needed(new_light_state):
            return

        self.log(f"light is set to {new_light_state and 'on' or 'off'}")

        self.expected_action = new_light_state and "on" or "off"

        if new_light_state:
            kwargs = {}
            if self.day_illuminance and self.night_illuminance:
                kwargs["brightness"] = self.calculate_light_brightness()
            self.turn_on(self.light_entity, **kwargs)
            return

        self.turn_off(self.light_entity)
