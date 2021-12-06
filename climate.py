import hassapi as hass
from datetime import time, datetime


class Radiator(hass.Hass):
    OFF_TEMP = 5

    window_contact_entity: str = None
    night_target_temp_entity: str = None
    day_target_temp_entity: str = None
    day_start_time_entity: str = None
    night_start_time_entity: str = None
    climate_entity: str = None
    is_away_entity: str = None

    def initialize(self) -> None:
        self.init_values()
        self.init_listeners()

    def init_values(self) -> None:
        self.window_contact_entity = self.args["window_contact"]
        self.night_target_temp_entity = self.args["night_target_temp"]
        self.day_target_temp_entity = self.args["day_target_temp"]
        self.day_start_time_entity = self.args["day_start_time"]
        self.night_start_time_entity = self.args["night_start_time"]
        self.climate_entity = self.args["climate"]
        self.is_away_entity = self.args["away"]

        self.handle_day_start: str = None
        self.handle_night_start: str = None

    def init_listeners(self) -> None:
        self.listen_state(self.update_target_temp, self.window_contact_entity)

        self.listen_state(self.update_target_temp,
                          self.night_target_temp_entity)
        self.listen_state(self.update_target_temp, self.day_target_temp_entity)
        self.listen_state(self.start_time_changed, self.day_start_time_entity)
        self.listen_state(self.start_time_changed,
                          self.night_start_time_entity)
        self.listen_state(self.update_target_temp, self.is_away_entity)

        self.init_time_listeners()

    def init_time_listeners(self) -> None:
        if self.handle_day_start is not None:
            self.cancel_timer(self.handle_day_start)
        if self.handle_night_start is not None:
            self.cancel_timer(self.handle_night_start)

        self.handle_day_start = self.run_daily(
            self.update_target_temp, self.get_time(self.day_start_time_entity))
        self.handle_night_start = self.run_daily(
            self.update_target_temp,
            self.get_time(self.night_start_time_entity))

    def start_time_changed(self, entity: str, attribute: str, old: str,
                           new: str, kwargs: dict) -> None:
        self.init_time_listeners()
        self.update_target_temp()

    def window_is_open(self) -> bool:
        return self.get_state(self.window_contact_entity) == "on"

    def is_away(self) -> bool:
        return self.get_state(self.is_away_entity) == "on"

    def is_night(self) -> bool:
        now = datetime.now().time()
        day_start_time = self.get_time(self.day_start_time_entity)
        night_start_time = self.get_time(self.night_start_time_entity)

        return now < day_start_time or now > night_start_time

    def calculate_target_temp(self) -> float:
        window_is_open = self.window_is_open()
        is_away = self.is_away()
        is_night = self.is_night()
        if (self.window_is_open()):
            return self.OFF_TEMP

        if self.is_night() or self.is_away():
            return self.get_state(self.night_target_temp_entity)
        return self.get_state(self.day_target_temp_entity)

    def set_target_temp(self, temp: float) -> None:
        self.call_service("climate/set_temperature",
                          entity_id=self.climate_entity,
                          temperature=temp)

    def update_target_temp(self, *_) -> None:
        target_temp = self.calculate_target_temp()
        self.log(f"Setting target temperature to {target_temp}")
        self.set_target_temp(target_temp)

    def get_time(self, entity: str) -> time:
        time_str = self.get_state(entity)
        return time.fromisoformat(time_str)