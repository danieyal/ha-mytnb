# Home Assistant myTNB Integration

Home Assistant custom component for [myTNB](https://www.mytnb.com.my). Monitor your Tenaga Nasional Berhad electricity accounts.

## Features

- **Account auto-discovery**: one login discovers all linked TNB accounts
- **Usage tracking**: current, average, and monthly kWh consumption
- **Cost monitoring**: current, projected, and monthly billing in RM
- **Bill history**: last payment date/amount, outstanding balance
- **Smart meter support**: SMR status per account
- **Rich attributes**: daily breakdown, tariff blocks, full bill history

## Installation

### HACS (recommended)

[![Open your Home Assistant instance and open a repository inside the Home Assistant Community Store.](https://my.home-assistant.io/badges/hacs_repository.svg)](https://my.home-assistant.io/redirect/hacs_repository/?owner=your-org&repository=ha-mytnb&category=integration)

Or

1. Add this repository as a custom repository in HACS
2. Search for **myTNB** in HACS and install

### Manual

Copy `custom_components/mytnb/` into your Home Assistant `custom_components/` directory.

## Configuration

1. Go to **Settings** → **Devices & Services** → **Add Integration**
2. Search for **myTNB**
3. Enter your myTNB email and password
4. All linked accounts are discovered automatically

## Sensors

For each discovered account (e.g. `220123456789`):

| Sensor | Unit | Description |
|---|---|---|
| `sensor.mytnb_<acc>_current_usage` | kWh | Current billing period usage |
| `sensor.mytnb_<acc>_average_usage` | kWh | Average daily usage |
| `sensor.mytnb_<acc>_current_cost` | RM | Current billing period cost |
| `sensor.mytnb_<acc>_projected_cost` | RM | Projected billing period cost |
| `sensor.mytnb_<acc>_monthly_usage` | kWh | Latest complete month usage |
| `sensor.mytnb_<acc>_monthly_cost` | RM | Latest complete month cost |
| `sensor.mytnb_<acc>_due_amount` | RM | Outstanding balance |
| `sensor.mytnb_<acc>_last_payment_amount` | RM | Last payment amount |
| `sensor.mytnb_<acc>_last_payment_date` | date | Last payment date |

Each sensor includes attributes for account details, daily usage, tariff blocks, and bill history.

## Requirements

- Home Assistant 2024.1 or later
- Malaysian IP address (TNB API blocks non-Malaysian connections)

## License

MIT
