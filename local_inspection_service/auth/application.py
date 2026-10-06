"""Authentication graph ownership for application composition."""
from ..runtime.identity import RequestIdentity
from .composition import AuthenticationServices, AuthenticationStorage, AuthenticationSettings
from .http_composition import AuthenticationHttp, AuthenticationHttpPolicy


class AuthenticationDomain:
    """Own identity/services; keep routing positions under the application composer."""
    def __init__(self, *, storage: AuthenticationStorage, settings: AuthenticationSettings):
        self.identity = RequestIdentity()
        self.services = AuthenticationServices(storage=storage, settings=settings, identity=self.identity)

    def http(self, policy: AuthenticationHttpPolicy) -> AuthenticationHttp:
        return AuthenticationHttp(self.services, self.identity, policy)
