"""Account-visible projections and public-network policy around explicit inputs."""
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from typing import Any

from .account_projections import AccountProjections
from .account_projection_ports import AccountAccess, AccountConfig, AccountModels, AccountMedia
from .public_network import PublicNetworkPolicy
from .public_network_ports import OriginPolicy, PublicEndpointPolicy, RuntimeDetailAccess

Record = dict[str, Any]


@dataclass(frozen=True)
class VisibilityAccess:
    current_auth_user: Callable[[], Callable[[], Record]]
    user_is_admin: Callable[[], Callable[[Record], bool]]
    user_has_permission: Callable[[], Callable[[Record, str], bool]]
    record_mutable_by_user: Callable[[], Callable[[Record, Record], bool]]
    record_visible_to_user: Callable[[], Callable[[Record, Record, str | None], bool]]


@dataclass(frozen=True)
class VisibilityConfiguration:
    accessory_uid: Callable[[], Callable[[Record], str]]
    training_state_for_user: Callable[[], Callable[[Record, Record, set[str], str | None], Record]]
    PLC_CAPTURE_RESULTS_KEY: Callable[[], str]
    load_config: Callable[[], Callable[[], Record]]


@dataclass(frozen=True)
class VisibilityOrigins:
    values: Callable[[], Sequence[str]]
    regex: Callable[[], str]


class AccountVisibility:
    def __init__(self, *, access: VisibilityAccess, configuration: VisibilityConfiguration,
                 models: AccountModels, media: AccountMedia, origins: VisibilityOrigins,
                 masked_url: Callable[[], Callable[[str], str]]):
        self.network = PublicNetworkPolicy(
            origins=OriginPolicy(lambda:self._normalize_origin, origins.values, origins.regex),
            endpoints=PublicEndpointPolicy(lambda:self._private_host, masked_url),
            access=RuntimeDetailAccess(access.user_is_admin, access.user_has_permission))
        self.projections = AccountProjections(
            access=AccountAccess(access.current_auth_user, access.user_is_admin,
                access.user_has_permission, lambda:self._runtime_details,
                access.record_mutable_by_user, access.record_visible_to_user),
            config=AccountConfig(configuration.accessory_uid, configuration.training_state_for_user,
                configuration.PLC_CAPTURE_RESULTS_KEY, lambda:self._scope_config,
                configuration.load_config), models=models, media=media)

    def _normalize_origin(self, value: str) -> str:
        return self.network.normalize_origin(value)

    def _private_host(self, hostname: str) -> bool:
        return self.network.is_private_or_local_host(hostname)

    def _runtime_details(self, user: Record | None) -> bool:
        return self.network.include_internal_runtime_details(user)

    def _scope_config(self, config: Record, user: Record | None = None,
                      target_user_id: str | None = None) -> Record:
        return self.projections.scope_config_for_user(config, user, target_user_id)
