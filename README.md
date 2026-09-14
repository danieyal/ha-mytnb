# Home Assistant myTNB Integration

A Home Assistant custom integration for [myTNB](https://www.mytnb.com.my). Monitor your Tenaga Nasional Berhad electricity accounts.

## Features

- **Account auto-discovery**: one login discovers all linked TNB accounts
- **Usage tracking**: current, average, and last completed month's kWh consumption
- **Cost monitoring**: current, projected, and last completed month's billing in RM
- **Bill history**: last payment date/amount, outstanding balance
- **Smart meter support**: SMR status per account
- **Rich attributes**: daily breakdown, tariff blocks, full bill history
- **Retry with backoff**: transient API failures are retried with exponential
  backoff + jitter at both the per-request level (in [python-mytnb](https://github.com/danieyal/python-mytnb))
  and the per-cycle level (in this integration), so a WAF blip doesn't surface
  as an unavailable entity

## Installation

### HACS (recommended)

[![Open your Home Assistant instance and open a repository inside the Home Assistant Community Store.](https://my.home-assistant.io/badges/hacs_repository.svg)](https://my.home-assistant.io/redirect/hacs_repository/?owner=ken-kargo&repository=ha-mytnb&category=integration)

Alternatively:

1. In HACS, go to **Integrations**
2. Open the **⋮** menu (top right) → **Custom repositories**
3. Add `https://github.com/ken-kargo/ha-mytnb` with category **Integration**
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

| Sensor                                   | Unit | Description                        |
| ---------------------------------------- | ---- | ---------------------------------- |
| `sensor.mytnb_<acc>_current_usage`       | kWh  | Current billing period usage       |
| `sensor.mytnb_<acc>_average_usage`       | kWh  | Average daily usage                |
| `sensor.mytnb_<acc>_current_cost`        | RM   | Current billing period cost        |
| `sensor.mytnb_<acc>_projected_cost`      | RM   | Projected billing period cost      |
| `sensor.mytnb_<acc>_last_month_usage`    | kWh  | Last completed billing month usage |
| `sensor.mytnb_<acc>_last_month_cost`     | RM   | Last completed billing month cost  |
| `sensor.mytnb_<acc>_due_amount`          | RM   | Outstanding balance                |
| `sensor.mytnb_<acc>_last_payment_amount` | RM   | Last payment amount                |
| `sensor.mytnb_<acc>_last_payment_date`   | date | Last payment date                  |
| `sensor.mytnb_<acc>_meter_reading`       | kWh  | Latest billed meter register reading |
| `sensor.mytnb_<acc>_current_meter_reading` | kWh | Current meter reading (extrapolated) |

Both meter-reading sensors depend on the latest bill PDF's meter-information section. The latest billed meter-reading sensor exposes its billed kWh register, while the extrapolated sensor adds myTNB's current billing-period usage to that register and automatically rebases when a new billing number appears. Both sensors include the meter number, previous reading, billed usage, and any kW/kVARh registers. This is a fragile integration point: either sensor can become unavailable if myTNB changes its bill-PDF layout or bill-download endpoint. May need maintenance before become usable if TNB updated their bill structures and breaks the meter reading attempts.

Each sensor includes attributes for account details, daily usage, tariff blocks, and bill history.

## Requirements

- Home Assistant 2024.1 or later
- Malaysian IP address (TNB API blocks non-Malaysian connections)

## Acknowledgements

Thanks to [@danieyal](https://github.com/danieyal) for the original [ha-mytnb](https://github.com/danieyal/ha-mytnb) project, which this integration forked from and modified for my own needs.

## License

MIT
