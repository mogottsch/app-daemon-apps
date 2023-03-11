from typing import Dict, List
import hassapi as hass
from datetime import timedelta, datetime


class Notifier(hass.Hass):
    mobile_target_enities: list = []
    media_player_entities: List[Dict] = []
    language: str = None
    night_mode_entity: str = None
    guest_sleeping_entity: str = None

    def initialize(self) -> None:
        self.init_values()

    def init_values(self) -> None:
        self.mobile_target_enities = self.args["mobile_targets"]
        self.media_player_entities = self.args["media_players"]
        self.language = self.args["language"]
        self.night_mode_entity = self.args["night_mode"]
        self.guest_sleeping_entity = self.args["guest_sleeping"]

    def is_night(self) -> bool:
        return self.get_state(self.night_mode_entity) == "on"

    def is_guest_sleeping(self) -> bool:
        return self.get_state(self.guest_sleeping_entity) == "on"

    def send_push_notification(self, message, title=None, tag=None) -> None:
        for entity in self.mobile_target_enities:
            self.log(f"Sending push notification to {entity}: {message}")
            service_name = f"notify/{entity}"

            data = {}
            if tag:
                data["tag"] = tag

            kwargs = {
                "message": message,
                "data": data,
            }

            if title:
                kwargs["title"] = title
            self.call_service(service_name, **kwargs)

    def say_message(self, message) -> None:
        if self.is_night():
            self.log(f"Night mode is enabled, tts cancelled")
            return

        if self.is_guest_sleeping():
            self.log(f"Guest is sleeping, tts cancelled")
            return

        for key, entity in self.media_player_entities.items():
            entity_id = entity["entity_id"]
            occupancy_entity_id = entity.get("occupancy_entity_id")
            if occupancy_entity_id and not self.is_occupied(occupancy_entity_id):
                self.log(f"{entity_id} is not occupied, tts cancelled")
                continue

            if self.get_state(entity_id) == "playing":
                self.log(f"{entity_id} is playing, tts cancelled")
                continue

            self.log(f"Broadcasting message through {key}: {message}")
            self.call_service(
                "tts/cloud_say",
                entity_id=entity_id,
                message=message,
                language=self.language,
            )

    def notify(
        self, message, title=None, only_push=False, only_say=False, tag=None
    ) -> None:
        if not only_push:
            self.say_message(message)

        if not only_say:
            self.send_push_notification(message, title, tag)

    def is_occupied(self, entity_id) -> bool:
        return self.get_state(entity_id) == "on"


class UseNotifier(hass.Hass):
    notifier: Notifier = None

    def initialize(self) -> None:
        self.notifier = self.get_app(self.args["notifier"])

    def notify(self, *args, **kwargs) -> None:
        self.notifier.notify(*args, **kwargs)


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
        self.throttle_duration = timedelta(seconds=self.args["throttle_duration"])
        self.is_enabled_entity = self.args["is_enabled"]

    def init_listeners(self) -> None:
        for key, sensor in self.window_sensors.items():
            self.listen_state(
                self.window_open_long,
                sensor["entity_id"],
                new="on",
                duration=self.duration.seconds,
            )

    def is_enabled(self) -> bool:
        self.log(self.get_state(self.is_enabled_entity))
        return self.get_state(self.is_enabled_entity) == "on"

    def window_open_long(self, entity, attribute, old, new, kwargs) -> None:
        if not self.is_enabled():
            self.log(
                f"Notifications for {entity} are disabled through {self.is_enabled_entity}"
            )
            return

        name = [
            sensor["name"]
            for key, sensor in self.window_sensors.items()
            if sensor["entity_id"] == entity
        ][0]

        if (
            self.last_notification is not None
            and self.last_notification + self.throttle_duration > datetime.now()
        ):
            self.log(f"Notification throttled for {name}")
            return

        duration_minutes = int(self.duration.seconds / 60)
        self.last_notification = datetime.now()
        self.notify(
            f"Das Fenster im {name} is seit {duration_minutes} Minuten offen.",
            tag="window_open_long",
        )


class PowerDropped(UseNotifier):
    power_sensor_entity: str
    power_threshold: int
    message: str

    def initialize(self) -> None:
        super().initialize()
        self.init_values()
        self.init_listeners()

    def init_values(self) -> None:
        self.power_sensor_entity = self.args["power_sensor"]
        self.power_threshold = self.args["power_threshold"]
        self.message = self.args["message"]

    def init_listeners(self) -> None:
        self.listen_state(
            self.power_dropped,
            self.power_sensor_entity,
        )

    def power_dropped(self, entity, attribute, old, new, kwargs) -> None:
        self.log(f"Power dropped: {new} from {old}")
        if int(new) > int(old) or int(new) > self.power_threshold:
            return
        self.notify(self.message, tag=f"power_dropped_{self.power_sensor_entity}")


class ErrorLogged(UseNotifier):
    def initialize(self) -> None:
        super().initialize()
        self.init_listeners()

    def init_listeners(self) -> None:
        self.listen_log(self.handle_error_log, level="WARNING")

    def handle_error_log(self, name, ts, level, type, message, kwargs) -> None:
        self.notify(f"Error logged: {message}", only_push=True, tag="error")


class NotificationHAService(UseNotifier):
    def initialize(self) -> None:
        self.log("Initializing notification service")
        super().initialize()
        handle = self.listen_event(self.call_notify, "appdaemon_notify")

    def call_notify(
        self,
        event_name,
        data,
        *args,
        **kwargs,
    ) -> None:
        if not "message" in data:
            raise Exception("Missing message in notification event from HA")
        self.notify(
            data["message"],
            title=data.get("title", None),
            tag=data.get("tag", None),
            only_push=data.get("only_push", False),
            only_say=data.get("only_say", False),
        )
