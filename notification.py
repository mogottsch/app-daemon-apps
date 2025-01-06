from appdaemon.adapi import Entity
import hassapi as hass
from appdaemon import adbase as ad


class Notifier(hass.Hass, ad.ADBase):
    mobile_target_enities: list[str]
    media_player_entities: dict[str, dict[str, str]]
    language: str
    night_mode_entity: Entity
    guest_sleeping_entity: Entity

    def initialize(self) -> None:
        self.init_values()

    def init_values(self) -> None:
        self.adapi = self.get_ad_api()
        self.mobile_target_enities = self.args["mobile_targets"]
        self.night_mode_entity = self.adapi.get_entity(self.args["night_mode"])
        self.guest_sleeping_entity = self.adapi.get_entity(self.args["guest_sleeping"])

        self.media_player_entities = self.args["media_players"]

        self.language = self.args["language"]

    def is_night(self) -> bool:
        return self.night_mode_entity.get_state() == "on"

    def is_guest_sleeping(self) -> bool:
        return self.guest_sleeping_entity.get_state() == "on"

    def send_push_notification(self, message, title=None, tag=None) -> None:
        for entity in self.mobile_target_enities:
            self.adapi.log(f"Sending push notification to {entity}: {message}")
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
            self.adapi.log(f"Night mode is enabled, tts cancelled")
            return

        if self.is_guest_sleeping():
            self.adapi.log(f"Guest is sleeping, tts cancelled")
            return

        for key, entity in self.media_player_entities.items():
            entity_id = entity["entity_id"]
            occupancy_entity_id = entity.get("occupancy_entity_id")
            if occupancy_entity_id and not self.is_occupied(occupancy_entity_id):
                self.adapi.log(f"{entity_id} is not occupied, tts cancelled")
                continue

            if self.get_state(entity_id) == "playing":
                self.adapi.log(f"{entity_id} is playing, tts cancelled")
                continue

            self.adapi.log(f"Broadcasting message through {key}: {message}")
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


class UseNotifier(ad.ADBase):
    notifier: Notifier

    def initialize(self) -> None:
        self.adapi = self.get_ad_api()
        self.notifier = self.adapi.get_app(self.args["notifier"])

    def notify(self, *args, **kwargs) -> None:
        self.notifier.notify(*args, **kwargs)


class NotificationHAService(UseNotifier):
    def initialize(self) -> None:
        self.adapi.log("Initializing notification service")
        super().initialize()
        handle = self.adapi.listen_event(self.call_notify, "appdaemon_notify")

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


class ErrorLogged(UseNotifier):
    def initialize(self) -> None:
        super().initialize()
        self.adapi = self.get_ad_api()
        self.init_listeners()

    def init_listeners(self) -> None:
        self.adapi.listen_log(self.handle_error_log, level="WARNING")

    def handle_error_log(self, name, ts, level, type, message, kwargs) -> None:
        self.adapi.log(f"Error logged: {message}")
        self.notify(f"Error logged: {message}", only_push=True, tag="error")
