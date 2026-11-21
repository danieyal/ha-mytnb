# Home Assistant myTNB Integration

A Home Assistant custom integration for [myTNB](https://www.mytnb.com.my). Monitor your Tenaga Nasional Berhad electricity accounts.

## Features

- **Account auto-discovery**: one login discovers all linked TNB accounts
- **Usage tracking**: current, average, and last completed month's kWh consumption
- **Cost monitoring**: current, projected, and last completed month's billing in MYR
- **Meter reading**: the meter's kWh register from your latest bill
- **Bill history**: last payment date/amount, outstanding balance
- **Smart meter support**: SMR status per account
- **Rich attributes**: daily breakdown, tariff blocks, full bill history
- **Retry with backoff**: transient API failures are retried with exponential
  backoff + jitter at both the per-request level (in [python-mytnb](https://github.com/danieyal/python-mytnb))
  and the per-cycle level (in this integration), so a WAF blip doesn't surface
  as an unavailable entity

## Installation

### HACS (recommended)

[![Open your Home Assistant instance and open a repository inside the Home Assistant Community Store.](https://my.home-assistant.io/badges/hacs_repository.svg)](https://my.home-assistant.io/redirect/hacs_repository/?owner=danieyal&repository=ha-mytnb&category=integration)

Alternatively:

1. In HACS, go to **Integrations**
2. Open the **⋮** menu (top right) → **Custom repositories**
3. Add `https://github.com/danieyal/ha-mytnb` with category **Integration**
4. Search for **myTNB** in HACS and install

### Manual

Copy `custom_components/mytnb/` into your Home Assistant `custom_components/` directory.

## Configuration

1. Go to **Settings** → **Devices & Services** → **Add Integration**
2. Search for **myTNB**
3. Enter your myTNB email and password
4. All linked accounts are discovered automatically

## Sensors

For each discovered account (e.g. `220123456789`):

| Sensor                                       | Unit | Description                                      |
| -------------------------------------------- | ---- | ------------------------------------------------ |
| `sensor.mytnb_<acc>_current_usage`           | kWh  | Current billing period usage                     |
| `sensor.mytnb_<acc>_average_usage`           | kWh  | Average daily usage                              |
| `sensor.mytnb_<acc>_current_cost`            | MYR  | Current billing period cost                      |
| `sensor.mytnb_<acc>_projected_cost`          | MYR  | Projected billing period cost                    |
| `sensor.mytnb_<acc>_last_month_usage`        | kWh  | Last completed billing month usage               |
| `sensor.mytnb_<acc>_last_month_cost`         | MYR  | Last completed billing month cost                |
| `sensor.mytnb_<acc>_due_amount`              | MYR  | Outstanding balance                              |
| `sensor.mytnb_<acc>_last_payment_amount`     | MYR  | Last payment amount                              |
| `sensor.mytnb_<acc>_last_payment_date`       | date | Last payment date                                |
| `sensor.mytnb_<acc>_meter_reading`           | kWh  | Meter reading on the latest bill                 |
| `sensor.mytnb_<acc>_estimated_meter_reading` | kWh  | Billed reading plus usage since (off by default) |

Each sensor includes attributes for account details, daily usage, tariff blocks, and bill history.

Money is in MYR, the ISO 4217 code Home Assistant expects, so the frontend formats it as currency. Versions before 1.5.0 used "RM"; updating relabels the statistics already recorded, so their history carries on.

### Meter reading

myTNB's API doesn't report the meter's own register reading; only the bill shows it. The integration downloads the bill PDF once per new bill and reads its meter table ("Maklumat Meter"). The **Meter reading** sensor is the kWh register at the end of the billed period, and its `meter_readings` attribute lists every register on the bill (kWh, plus kW and kVARh on some tariffs) with the previous reading and the usage billed.

**Estimated meter reading** adds this billing period's usage to that reading. It is off by default and keeps no long-term statistics: the bill and the usage figure update separately, so around bill day the sum can be a month off for a while.

If TNB changes the bill layout, both sensors become unknown and the log says the bill has no meter readings this version can read. The other sensors are unaffected.

## Requirements

- Home Assistant 2024.1 or later
- Malaysian IP address (TNB API blocks non-Malaysian connections)

## License

MIT
