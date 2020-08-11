# tap-tradetracker

This is a [Singer](https://singer.io) tap that produces JSON-formatted data following the [Singer spec](https://github.com/singer-io/getting-started/blob/master/SPEC.md).

This tap retrieves data from the TradeTracker.com [Web service](https://merchant.tradetracker.com/webService) (SOAP API)

## tap config

| config entry         | type         | mandatory / default value | description |
| -------------------- | ------------ | ------------------------- | -------------------------------- |
| `customer_id`        | integer      | yes                       | The customer ID as supplied by TradeTracker. |
| `passphrase`         | string or string-array | yes                       | A list of passphrases as supplied by TradeTracker. Each country has an individual phassphrase. When you just want to sync. one country, you can provide just a single string |
| `sandbox`            | boolean      | no, false                 | If sandbox mode is enabled, it is safe to perform manipulation operations without really affecting anything. |
| `locale`             | string       | no, (customer-locale)     | If a locale is specified, all data returned will be in this specific locale. By default, data is returned in the customer's locale. |
| `demo`               | boolean      | no, false                 | If demo mode is enabled, instead of the regular data, demo data will be loaded. |
| `start_date`         | date         | no                        | The start date if no bootmark value is provided for a date-ranged stream (e.g. an report) |
| `attribution_window` | integer      | no, default: 30           | The attribution window for a date-ranged stream (e.g. an report) |

### Sample config

```
{
    "customer_id": 123456789,
    "passphrase": ["9e591a8b8a71bf10a916610f851b14bbe8a1bcd3","a4a68b43de497242386901350261a26f7da95a7c","7141ffebaa87db550882aa93862abccc911a7402","279676b5a66b5dcf80e9bddf6e0fed81f4b632a4"],
    "sandbox": false,
    "locale": "en_GB",
    "demo": false,
    "start_date": "2020-01-01",
    "attribution_window": 7
}
```
