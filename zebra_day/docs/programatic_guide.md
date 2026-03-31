# zebra_day Programmatic Guide

## Client Split

`zebra_day` now exposes two supported Python clients:

- `ZebraDayClient`: direct TapDB access for the zebra_day service and admin/runtime tooling
- `ZebraDayApiClient`: remote API access for downstream apps that need shared fleet state without direct TapDB access

## Direct TapDB Client

Use this inside the zebra_day service or trusted admin tooling where direct TapDB connectivity is intended.

```python
from zebra_day import ZebraDayClient, ZebraDaySettings

settings = ZebraDaySettings.from_context("local")
client = ZebraDayClient(settings)

labs = client.list_labs()
printers = client.list_printers("default")
template_names = client.list_templates()
```

`ZebraDayClient` fails fast if TapDB config or connectivity is missing.

Common operations:

```python
client.save_template("tube_2inX1in", "^XA^FO30,30^FDHello^FS^XZ")
client.render_label(template="tube_2inX1in", uid_barcode="SAMPLE-001")
client.print_label(
    lab="default",
    printer="printer-1",
    label_zpl_style="tube_2inX1in",
    uid_barcode="SAMPLE-001",
)
client.discover_printers(ip_stub="192.168.1", lab="default")
```

## Remote API Client

Use this in downstream apps such as Bloom.

```python
from zebra_day import ZebraDayApiClient

with ZebraDayApiClient("https://localhost:8118", api_key="internal-token") as client:
    printers = client.list_printers("default")
    template = client.get_template("tube_2inX1in")
    resolved = client.resolve_print_request(
        lab="default",
        printer="printer-1",
        label_zpl_style="tube_2inX1in",
        uid_barcode="SAMPLE-001",
    )
```

There are two print paths:

- `print_label(...)`: fetch shared config remotely, then send ZPL directly to the printer from the local process
- `submit_print_job(...)`: submit the job back to the zebra_day API for server-side delivery

Example:

```python
from zebra_day import ZebraDayApiClient

with ZebraDayApiClient("https://localhost:8118", api_key="internal-token") as client:
    client.submit_print_job(
        lab="default",
        printer="printer-1",
        label_zpl_style="tube_2inX1in",
        uid_barcode="SAMPLE-001",
    )
```

## Data Model Notes

Shared state is resolved from TapDB-backed records for:

- printers
- label templates
- label profiles
- printer observations
- metadata drift records
- print jobs

Templates and profiles are no longer loaded from local user directories at runtime.
