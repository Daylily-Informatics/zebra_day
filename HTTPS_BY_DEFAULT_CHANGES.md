# HTTPS by Default Implementation

## Summary

Updated the `zday gui start` command to enforce HTTPS by default with automatic certificate generation using mkcert.

## Changes Made

### 1. Enhanced `zebra_day/mkcert.py`

**Added:**
- `get_platform_install_command()`: Returns platform-specific mkcert installation commands
  - macOS: `brew install mkcert`
  - Ubuntu/Debian: `sudo apt install mkcert`
  - Fedora/RHEL: `sudo dnf install mkcert`
  - Windows: `choco install mkcert`
  
- `try_auto_generate_certificates()`: Attempts automatic certificate generation
  - Returns: `(success, message, cert_path, key_path)`
  - Checks if certificates already exist
  - Verifies mkcert is installed
  - Verifies CA is installed
  - Attempts to generate certificates
  - Provides actionable error messages on failure

### 2. Updated `zebra_day/cli/gui.py`

**Modified `_resolve_ssl_paths()`:**
- Added `no_https` parameter
- Changed return type to include status message: `(cert_path, key_path, use_https, status_message)`
- Attempts automatic certificate generation when no existing certificates found
- Provides detailed status messages for all scenarios

**Modified `start` command:**
- Updated docstring to reflect HTTPS-by-default behavior
- Improved status reporting with detailed messages
- Shows certificate generation status
- Displays actionable guidance when HTTPS setup fails

**Modified `status` command:**
- Updated to handle new `_resolve_ssl_paths()` signature

### 3. Updated `zebra_day/web/app.py`

**Modified `run_server()`:**
- Updated docstring to document HTTPS-by-default behavior
- Added automatic certificate generation attempt when no certificates found
- Improved logging with detailed status messages
- Falls back to HTTP with guidance when certificate setup fails

### 4. Updated `zebra_day/__init__.py`

**Modified `start_gui()`:**
- Updated docstring to reflect HTTPS-by-default with auto-generation
- Updated examples to show new behavior

### 5. Added `tests/test_mkcert.py`

**New test coverage:**
- Platform detection tests (macOS, Ubuntu, Windows)
- mkcert installation checks
- CA installation checks
- Certificate existence checks
- Certificate generation tests
- Auto-generation workflow tests (15 tests total)

## Behavior

### Default Behavior (HTTPS Enabled)

When running `zday gui start` without flags:

1. **Check for existing certificates** in priority order:
   - Explicit `--cert/--key` arguments
   - `SSL_CERT_PATH/SSL_KEY_PATH` environment variables
   - Default path: `~/.config/zebra_day/certs/`

2. **Attempt auto-generation** if no certificates found:
   - Check if `mkcert` is installed
   - Check if CA is installed (`mkcert -CAROOT` and verify `rootCA.pem`)
   - Generate certificates using `mkcert.generate_certificates()`

3. **Fall back to HTTP** with guidance if auto-generation fails:
   - If mkcert not installed: Show installation command for user's platform
   - If CA not installed: Instruct to run `mkcert -install`
   - If generation fails: Show manual generation commands

### HTTP Mode

Use `--no-https` flag to explicitly disable HTTPS and run in HTTP mode.

## Status Reporting

The server now clearly indicates:
- Whether HTTPS or HTTP mode is active
- Certificate paths when HTTPS is enabled
- Reason for HTTP mode if HTTPS was attempted but failed
- Actionable guidance for setting up HTTPS

## Examples

### Successful HTTPS (existing certificates)
```
✓ HTTPS enabled
  Certificate: /Users/user/.config/zebra_day/certs/server.crt
  Private key: /Users/user/.config/zebra_day/certs/server.key
✓ Server started (PID 12345)
  URL: https://0.0.0.0:8118
```

### Successful HTTPS (auto-generated)
```
✓ HTTPS enabled
  Certificate: /Users/user/.config/zebra_day/certs/server.crt
  Private key: /Users/user/.config/zebra_day/certs/server.key
  Successfully generated certificates at /Users/user/.config/zebra_day/certs/server.crt
✓ Server started (PID 12345)
  URL: https://0.0.0.0:8118
```

### HTTP fallback (mkcert not installed)
```
⚠ Running in HTTP mode (insecure)
  mkcert is not installed. Install it with:
  brew install mkcert
  Then run: mkcert -install
✓ Server started (PID 12345)
  URL: http://0.0.0.0:8118
```

### HTTP mode (explicit)
```
⚠ Running in HTTP mode (insecure)
  HTTP mode (--no-https flag)
✓ Server started (PID 12345)
  URL: http://0.0.0.0:8118
```

## Testing

All existing tests pass (167 tests), plus 15 new tests for mkcert functionality.

Run tests:
```bash
pytest tests/test_mkcert.py -v
pytest tests/ -v
```

