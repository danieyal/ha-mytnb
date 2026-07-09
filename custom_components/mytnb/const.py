from datetime import timedelta

DOMAIN = "mytnb"
PLATFORMS = ["sensor"]

# Retry/backoff defaults for the integration's high-level API operations.
# These mirror python-mytnb's internal transport retry so that transient
# failures which slip past the library's per-request retries get a bounded
# second chance with the same exponential-with-jitter cadence.
DEFAULT_RETRY_ATTEMPTS = 3
DEFAULT_RETRY_BASE_DELAY = 0.5  # seconds
DEFAULT_RETRY_BACKOFF_FACTOR = 2  # delay grows as base_delay * factor**attempt

CONF_EMAIL = "email"
CONF_PASSWORD = "password"
CONF_ACCOUNTS = "accounts"
CONF_ACCOUNT_NUMBER = "account_number"
CONF_OWNER_NAME = "owner_name"
CONF_IS_OWNED = "is_owned"

DEFAULT_POLL_INTERVAL = timedelta(hours=1)

MANUFACTURER = "Tenaga Nasional Berhad"
MODEL = "myTNB Account"

ATTR_ACCOUNT_NUMBER = "account_number"
ATTR_OWNER_NAME = "owner_name"
ATTR_ADDRESS = "address"
ATTR_IS_SMART_METER = "is_smart_meter"
ATTR_DAILY_USAGE = "daily_usage"
ATTR_BILL_HISTORY = "bill_history"
ATTR_PAYMENT_HISTORY = "payment_history"
ATTR_TARIFF_BLOCKS = "tariff_blocks"
ATTR_DUE_DATE = "due_date"
