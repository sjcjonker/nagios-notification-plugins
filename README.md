# Nagios notification plugins

Small, dependency-light notification handlers for Nagios Core:

- `notify_by_pushover.sh`: host and service alerts through Pushover.
- `notify-lametric.py`: host and service alerts on a LaMetric Time device.

Microsoft Teams is deliberately out of scope. Both handlers can consume Nagios
environment macros directly, so secrets do not need to appear in Nagios command
arguments or process listings.

## Requirements

- Linux
- Bash 4 or newer and `curl` for Pushover
- Python 3.9 or newer for LaMetric
- A root-readable configuration file, recommended mode `0600`

Install the handlers in `/usr/lib/nagios/plugins/` and copy
`examples/notifications.env.example` to
`/etc/nagios4/private/notifications.env`. Never commit the populated file.

The example Nagios command definitions use environment macros and are available
in `examples/commands.cfg`.

## Direct use

```console
notify_by_pushover.sh -t 'Test' -m 'Pushover works'
notify-lametric.py -H 192.0.2.10 -l WARNING -m 'LaMetric works'
```

Use `--help` for all options. LaMetric notifications are never silently
suppressed unless `--silent-window` or `LAMETRIC_SILENT_WINDOW` is configured.

## Test

```console
python3 -m unittest discover -s tests -v
bash -n plugins/notify_by_pushover.sh
python3 -m py_compile plugins/notify-lametric.py
```

The tests do not contact Pushover or a LaMetric device.

## Security note

Pushover is contacted over HTTPS. LaMetric's local device API uses HTTP with
Basic authentication, as specified by LaMetric. Keep the device API on a
trusted management LAN and never expose port 8080 to an untrusted network.

## License

Copyright 2026 Stijn Jonker. Licensed under GPL-3.0-or-later. See `LICENSE`.
