# Diagnose Gemini image matching

The old message "AI matching could not finish" did not identify a cause. It could
represent an API rejection, timeout, blocked image, or invalid model output. This
update provides safe diagnostic codes instead of guessing which one occurred.

## Install the update

Back up your application and database. Replace project source with this ZIP's
`lost_and_found` files, preserving your `.env`, `media/`, database, and virtual
environment. Dependencies have not changed. No new migrations are needed.
Activate your virtual environment and run commands beside `manage.py`.

Ensure your `.env` includes:

```dotenv
AI_ENABLED=True
GEMINI_API_KEY=your-real-key-not-this-placeholder
GEMINI_MODEL=gemini-2.5-flash
GEMINI_TIMEOUT_SECONDS=60
```

Use an actual key from Google AI Studio. Restart Django whenever configuration
changes. A system/terminal environment variable takes precedence over `.env`;
the diagnostic warns if an existing key variable overrides the file without
printing either value.

## Run the diagnosis

```powershell
python manage.py check_ai
```

This sends two small test requests using generated object drawings, not your
stored reports or uploaded photos. It consumes a small amount of API quota.
It checks the photo feature schema, multiple-image input and structured JSON.
Keys and raw provider responses are never printed.

When successful, the command prints `PASS`. When unsuccessful, its final
`CommandError: [CODE] ...` line contains a safe reason and suggested action.
Share that line for troubleshooting; do not share your API key or `.env`.

| Code | Action |
|---|---|
| `NOT_CONFIGURED` | Enable AI and replace the placeholder key in `.env`. Restart Django. |
| `INVALID_KEY` | Copy a valid Gemini key from AI Studio, or replace a revoked/expired/leaked key. |
| `PERMISSION_DENIED` | Check project permissions, Gemini API enablement, and key restrictions. Keep restrictions appropriate for server-side use. |
| `QUOTA_EXCEEDED` | Check the project's AI Studio usage/rate limits. Wait for a temporary rate limit to reset. Zero or exhausted quota needs an eligible plan/quota; repeated retries do not fix it. |
| `BILLING_REQUIRED` | Review the project's available credits/plan in AI Studio. Enabling paid billing can incur charges. |
| `MODEL_NOT_FOUND` | List accessible models using the command below and configure an image-capable generateContent model. |
| `INVALID_REQUEST` | Verify the selected model supports image input and structured JSON. Use this updated source; run the diagnostic to identify which step fails. |
| `TIMEOUT` | Narrow the search filters. Increase `GEMINI_TIMEOUT_SECONDS` if necessary (10–120 seconds), then restart Django. |
| `CONNECTION` | Check internet access, DNS, firewall and proxy access to `generativelanguage.googleapis.com`. |
| `TLS_ERROR` | Check system time and trusted certificates/proxy configuration. Do not disable TLS certificate validation. |
| `PROVIDER_BUSY` | Wait and retry; check Google's service status. Temporary 5xx responses are retried once by the application. |
| `BLOCKED` | Try a clear photo of the object without people or private documents. |
| `TRUNCATED` / `INVALID_RESPONSE` | Retry with fewer candidates/clearer photos. Incomplete results are rejected, not presented as proof. |
| `IMAGE_UNREADABLE` | Replace the query photo or restore missing found-item image files. |

To inspect model access without a generation request:

```powershell
python manage.py check_ai --list-models
```

This list confirms `generateContent` support only. It does not guarantee image
or structured-output support, or usable quota. Choose a suitable image-capable
model and rerun `check_ai` after changing `GEMINI_MODEL`.

## After PASS

1. Stop the existing Django server with Ctrl+C and restart `python manage.py runserver`.
2. As a finder, upload a found-item report **with an image**.
3. As an administrator, approve it.
4. Sign in as a **different user**, then open **Search by image**.
5. Upload your missing item's photo, optionally filter category/location, consent,
   and submit. Your own found reports are deliberately excluded from claim searches.

The optional demo reports have no uploaded photos. Add photos to them and approve
the edited reports before using them as visual-search candidates. Returned,
claimed, rejected, closed and pending reports are excluded. Scores below 60 are
not shown as close matches, and at most 12 ranked candidates are compared.

If the diagnostic passes but browser search fails, share the new bracketed code
from the page. If it succeeds but shows no matches, check eligibility/compared
counts and try the manual found-item search. No algorithm guarantees recovery or
proves ownership; human verification still applies.

References: [Google's troubleshooting guide](https://ai.google.dev/gemini-api/docs/troubleshooting),
[API key setup](https://ai.google.dev/gemini-api/docs/api-key), and
[model lifecycle information](https://ai.google.dev/gemini-api/docs/deprecations).

## Changes in this update

Safe categorized errors replace the generic UI failure; a configurable 60-second
read timeout replaces 20 seconds. Transient server errors receive one bounded
retry, while quota/authentication errors do not. Multipart answers are joined
without thought parts before schema validation. Comparisons constrain the result
array length and candidate IDs, while retaining independent result validation.

Live Gemini was not verified during development because no actual key was
provided. Tests mock provider responses. The diagnostic lets you check the real
account and network without exposing your credentials.
