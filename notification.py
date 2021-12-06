from typing import Dict
import hassapi as hass
from datetime import timedelta, datetime


class Notifier(hass.Hass):
    mobile_target_enities: list = []
    media_player_entities: list = []
    language: str = None
    night_mode_entity: str = None

    def initialize(self) -> None:
        self.init_values()

    def init_values(self) -> None:
        self.mobile_target_enities = self.args["mobile_targets"]
        self.media_player_entities = self.args["media_players"]
        self.language = self.args["language"]
        self.night_mode_entity = self.args["night_mode_entity"]

    def is_night(self) -> bool:
        return self.get_state(self.night_mode_entity) == "on"

    def send_push_notification(self, message, title=None) -> None:
        for entity in self.mobile_target_enities:
            self.log(f"Sending push notification to {entity}: {message}")
            service_name = f"notify/{entity}"
            kwargs = {
                "message": message,
            }
            if title:
                kwargs["title"] = title
            self.call_service(service_name, **kwargs)

    def say_message(self, message) -> None:
        if self.is_night():
            self.log(f"Night mode is enabled, tts cancelled")
            return

        for entity in self.media_player_entities:
            self.log(f"Broadcasting message through {entity}: {message}")
            entity_id = f"media_player.{entity}"
            self.call_service("tts/cloud_say",
                              entity_id=entity_id,
                              message=message,
                              language=self.language)

    def notify(self, message, title=None, only_push=False) -> None:
        self.send_push_notification(message, title)
        if not only_push:
            self.say_message(message)


class UseNotifier(hass.Hass):
    notifier: Notifier = None

    def initialize(self) -> None:
        self.notifier = self.get_app(self.args["notifier"])

    def notify(self, message, title=None) -> None:
        self.notifier.notify(message, title)


class WindowOpenLong(UseNotifier):
    window_sensors: Dict[str, Dict[str, str]] = None
    duration: timedelta = None
    throttle_duration: timedelta = None
    last_notification: datetime = None

    def initialize(self) -> None:
        super().initialize()
        self.init_values()
        self.init_listeners()

    def init_values(self) -> None:
        self.window_sensors = self.args["window_sensors"]
        self.duration = timedelta(seconds=self.args["duration"])
        self.throttle_duration = timedelta(
            seconds=self.args["throttle_duration"])

    def init_listeners(self) -> None:
        for key, sensor in self.window_sensors.items():
            self.listen_state(self.window_open_long,
                              sensor["entity_id"],
                              new="on",
                              duration=self.duration.seconds)

    def window_open_long(self, entity, attribute, old, new, kwargs) -> None:
        name = [
            sensor['name'] for key, sensor in self.window_sensors.items()
            if sensor["entity_id"] == entity
        ][0]

        if self.last_notification is not None and \
             self.last_notification + self.throttle_duration > datetime.now(
        ):
            self.log(f"Notification throttled for {name}")
            return

        duration_minutes = int(self.duration.seconds / 60)
        self.last_notification = datetime.now()
        self.notify(
            f"Das Fenster im {name} is seit {duration_minutes} Minuten offen.")
