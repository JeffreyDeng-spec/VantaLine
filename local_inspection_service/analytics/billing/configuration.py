"""Private operator configuration and explicit reuse of mounted COS credentials.

Reads contain no application imports, supplier operations or mutation. Only an
operator-written payer mapping can select the two reserved COS references.
"""
import json
import os
from pathlib import Path
import stat

from .types import BillingError, payers

ACCOUNT_ENV = 'VANTALINE_BILLING_ACCOUNTS_JSON'
COS_REFERENCES = {
    'VANTALINE_BILLING_COS_SECRET_ID': 'COS_SECRET_ID',
    'VANTALINE_BILLING_COS_SECRET_KEY': 'COS_SECRET_KEY',
}


def unique_object(pairs):
    value = {}
    for key, item in pairs:
        if key in value:
            raise ValueError('duplicate configuration field')
        value[key] = item
    return value


def private_json(path):
    """Terminal symlinks, hard links, devices and public files are rejected."""
    descriptor = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    with os.fdopen(descriptor, 'rb') as stream:
        metadata = os.fstat(stream.fileno())
        if (not stat.S_ISREG(metadata.st_mode) or metadata.st_mode & 0o077
                or metadata.st_nlink != 1 or metadata.st_size > 65536
                or metadata.st_uid not in {0, os.getuid()}):
            raise ValueError('invalid private configuration file')
        raw = stream.read(65537)
        if len(raw) > 65536:
            raise ValueError('private configuration limit')
    return json.loads(raw, object_pairs_hook=unique_object)


class BillingConfiguration:
    def __init__(self, environment, data_directory, existing_secret):
        self.values = environment
        self.path = Path(data_directory) / 'billing_accounts.local.json'
        self.existing_secret = existing_secret

    def environment(self):
        # An explicit runtime value, including [] or empty, owns precedence.
        if ACCOUNT_ENV in self.values:
            return self.checked(self.values)
        try:
            accounts = private_json(self.path)
        except FileNotFoundError:
            return self.values
        except Exception:
            raise BillingError('billing_configuration_invalid') from None
        return self.checked({**self.values, ACCOUNT_ENV: json.dumps(accounts, ensure_ascii=False)})

    @staticmethod
    def checked(environment):
        for payer in payers(environment):
            if (payer.key_ref in COS_REFERENCES or payer.secret_ref in COS_REFERENCES) and (
                    payer.provider != 'tencent'
                    or payer.key_ref != 'VANTALINE_BILLING_COS_SECRET_ID'
                    or payer.secret_ref != 'VANTALINE_BILLING_COS_SECRET_KEY'):
                raise BillingError('billing_configuration_invalid')
        return environment

    def secret(self, name):
        existing = self.existing_secret(name)
        if existing or name not in COS_REFERENCES:
            return existing
        directory = self.values.get('CREDENTIALS_DIRECTORY', '')
        if not directory:
            return ''
        try:
            credentials = private_json(Path(directory) / 'cos-credentials.json')
            if credentials.get('COS_SESSION_TOKEN'):
                raise BillingError('billing_temporary_credential_unsupported')
            value = credentials.get(COS_REFERENCES[name], '')
            if not isinstance(value, str):
                raise ValueError('invalid credential material')
            return value
        except BillingError:
            raise
        except Exception:
            raise BillingError('credentials_missing') from None
