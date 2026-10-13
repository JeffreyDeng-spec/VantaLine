"""Exact money and validated, private payer configuration."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from decimal import Decimal, InvalidOperation, localcontext, ROUND_DOWN
import hashlib
import json
import re
from zoneinfo import ZoneInfo

PROVIDERS = {"volc": "火山引擎", "ali": "阿里云", "runpod": "RunPod", "tencent": "腾讯云", "gemini": "Gemini", "codex": "Codex"}
SUPPORTED = frozenset(("volc", "ali", "tencent", "runpod"))


class BillingError(Exception):
    """Fixed public code; never includes provider messages or credentials."""
    def __init__(self, code="provider_unavailable"):
        self.code = code
        super().__init__(code)


def decimal(value) -> Decimal:
    if value is None or isinstance(value, bool):
        raise BillingError("invalid_provider_amount")
    try:
        result = Decimal(str(value))
    except (InvalidOperation, ValueError):
        raise BillingError("invalid_provider_amount") from None
    if not result.is_finite() or result.copy_abs() > Decimal("1e18") or result.as_tuple().exponent < -64:
        raise BillingError("invalid_provider_amount")
    return result


def amount(value) -> str:
    return format(decimal(value), "f")


def total(values) -> str:
    with localcontext() as context:
        context.prec = 128
        return amount(sum((decimal(v) for v in values), Decimal(0)))


def subtract(left, right) -> Decimal:
    with localcontext() as context:
        context.prec = 128
        return decimal(left)-decimal(right)


def divide(left, right, *, places=None) -> Decimal:
    with localcontext() as context:
        context.prec = 128
        value=decimal(left)/decimal(right)
        return value.quantize(Decimal(1).scaleb(-places), rounding=ROUND_DOWN) if places is not None else value


def mean(values, count) -> str:
    result=format(divide(total(values),count,places=12),'f')
    return result.rstrip('0').rstrip('.') if '.' in result else result


def period_value(value: str | None, now: float) -> str:
    current = datetime.fromtimestamp(now, ZoneInfo("Asia/Shanghai")).date()
    value = value or current.strftime("%Y-%m")
    if not re.fullmatch(r"\d{4}-(0[1-9]|1[0-2])", value):
        raise BillingError("invalid_period")
    year, month = map(int, value.split("-"))
    age = (current.year-year)*12 + current.month-month
    if not 0 <= age < 18:
        raise BillingError("invalid_period")
    return value


def month_dates(period: str):
    year, month = map(int, period.split("-"))
    first = date(year, month, 1)
    after = date(year+1, 1, 1) if month == 12 else date(year, month+1, 1)
    return first, after-timedelta(days=1)


def safe_text(value, limit=160):
    return str(value or "")[:limit]


@dataclass(frozen=True)
class Payer:
    id: str
    provider: str
    payer_id: str = field(repr=False)
    alias: str = ""
    site: str = "cn"
    currency: str = "CNY"
    key_ref: str = field(default="", repr=False)
    secret_ref: str = field(default="", repr=False)
    resources: dict[str, str] = field(default_factory=dict, repr=False)
    pending: str = ""

    @property
    def timezone(self):
        return "UTC" if self.provider == "runpod" else "Asia/Shanghai"


def payers(environment) -> list[Payer]:
    """No secrets in this JSON. Identity deduplicates provider/site/payer."""
    try:
        items = json.loads(environment.get("VANTALINE_BILLING_ACCOUNTS_JSON", "[]"))
        if not isinstance(items, list) or len(items) > 32:
            raise ValueError()
        result, seen = [], set()
        for item in items:
            if not isinstance(item, dict) or set(item)-{"provider", "payer_id", "alias", "site", "currency", "key_ref", "secret_ref", "resource_projects"}:
                raise ValueError()
            provider = item["provider"]
            if provider not in PROVIDERS:
                raise ValueError()
            payer_id = str(item["payer_id"])
            if not re.fullmatch(r"[A-Za-z0-9_.@-]{1,128}", payer_id):
                raise ValueError()
            site, currency = item.get("site", "cn"), item.get("currency", "USD" if provider in {"runpod", "gemini", "codex"} else "CNY")
            if site not in {"cn", "international"} or currency not in {"CNY", "USD", "JPY"}:
                raise ValueError()
            refs = [item.get("key_ref", ""), item.get("secret_ref", "")]
            if any(ref and not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]{0,127}", ref) for ref in refs):
                raise ValueError()
            identity = f"{provider}:{site}:{payer_id}"
            if identity in seen:
                raise ValueError()
            seen.add(identity)
            resources = item.get("resource_projects", {})
            if not isinstance(resources, dict) or len(resources) > 5000 or any(not isinstance(k, str) or not isinstance(v, str) or not 1 <= len(k) <= 200 or v not in {"vantaline", "other"} for k, v in resources.items()):
                raise ValueError()
            identifier = "payer_"+hashlib.sha256(identity.encode()).hexdigest()[:24]
            result.append(Payer(identifier, provider, payer_id, safe_text(item.get("alias") or PROVIDERS[provider], 80), site, currency, *refs, resources, "billing_source_unverified" if provider not in SUPPORTED else ""))
        for provider in PROVIDERS:
            if not any(p.provider == provider for p in result):
                result.append(Payer("pending_"+provider, provider, "", PROVIDERS[provider], currency="USD" if provider in {"runpod", "gemini", "codex"} else "CNY", pending="billing_source_unverified" if provider not in SUPPORTED else "credentials_missing"))
        return sorted(result,key=lambda p:(list(PROVIDERS).index(p.provider),p.alias,p.id))
    except (ValueError, TypeError, KeyError):
        raise BillingError("billing_configuration_invalid") from None


def entry(identifier, day, service, net, *, resource="", gross=None, discount=None, granularity="bill", provider_record_id=None, payer: Payer):
    if not identifier or not re.fullmatch(r"\d{4}-\d{2}-\d{2}", day):
        raise BillingError("invalid_provider_record")
    date.fromisoformat(day)
    return {"id": hashlib.sha256(str(identifier).encode()).hexdigest(), "provider_record_id": safe_text(provider_record_id if provider_record_id is not None else identifier,128) if granularity=='bill' or provider_record_id else None, "day": day, "service": safe_text(service), "resource": safe_text(resource, 200), "net": amount(net), "gross": None if gross is None else amount(gross), "discount": None if discount is None else amount(discount), "currency": payer.currency, "project": payer.resources.get(resource, "unknown"), "granularity": granularity}


@dataclass(frozen=True)
class Balance:
    value: str
    components: dict[str, str | None]
    source: str


@dataclass(frozen=True)
class Bills:
    entries: list[dict]
    official_total: str | None
    complete_until: str | None
    source: str
    scope: str = "payer"
    summary_basis: str = "official_summary"
    daily: list[dict] = field(default_factory=list)

    def validated(self, payer: Payer, period: str):
        unique = {}
        for row in self.entries:
            if row["currency"] != payer.currency or not row["day"].startswith(period):
                raise BillingError("billing_scope_mismatch")
            previous = unique.get(row["id"])
            if previous is not None and previous != row:
                raise BillingError("conflicting_provider_record")
            unique[row["id"]] = row
        # Exact duplicate rows from repeated pages do not inflate consumption.
        return Bills(list(unique.values()), None if self.official_total is None else amount(self.official_total), self.complete_until, self.source, self.scope, self.summary_basis, self.daily)
