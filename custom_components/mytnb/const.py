from datetime import timedelta

DOMAIN = "mytnb"
PLATFORMS = ["sensor"]

CONF_EMAIL = "email"
CONF_PASSWORD = "password"

DEFAULT_POLL_INTERVAL = timedelta(hours=1)

ATTR_ACCOUNT_NUMBER = "account_number"
ATTR_OWNER_NAME = "owner_name"
ATTR_ADDRESS = "address"
ATTR_IS_SMART_METER = "is_smart_meter"
ATTR_DAILY_USAGE = "daily_usage"
ATTR_BILL_HISTORY = "bill_history"
ATTR_TARIFF_BLOCKS = "tariff_blocks"
