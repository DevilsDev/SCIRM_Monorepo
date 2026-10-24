# Scheduled reports

A **supplier risk digest** by email, daily, weekly or monthly. It lists what is new since
the previous report:
- **public records naming your suppliers**: FDA recalls, shortages, warning letters and
  import alerts, one line per recall event, with a link to the source
- **regulatory watch matches**: new FDA and EMA records naming a substance or product on
  your [watchlist](regulatory-watch.md)
- **disaster exposures**: GDACS alerts near a supplier's site, or in its country when its
  sites are unknown

It uses the same matching rules as the supplier panel and the [webhooks](webhooks.md); the
detector records these events for every organization whether or not it uses webhooks.
Each email says that these are records matched by name and alerts matched by location,
not findings about a supplier.

## Setting up

An administrator opens **Administration → Integrations → Scheduled reports**:
- **Name** and **how often**: daily, weekly on a chosen day, or monthly on the 1st.
- **Time** in UTC. The list shows each hour in your local time too.
- **Recipients**: members of your organization only. They are checked when the schedule is
  saved and again when the report is sent, so someone who leaves stops receiving it.
- **Don't send when there is nothing new**: otherwise a short "nothing new" email is sent.

**Send now** sends the report within about a minute, covering the period since the last
report; the regular schedule continues afterwards. **Pause** stops it. Resuming picks up at
the next scheduled time, without catching up on missed ones. Each schedule shows its next
run and the result of the last one. Creating and deleting schedules are recorded in the
[audit log](audit-log.md).

The first report covers the previous day, week or month. Events are only recorded from
the time the webhook detector first ran for the organization, so a new deployment's
first report can be short.

## Email settings

The coordinator sends the email; the gateway only reads whether email is configured.

| Variable | Default | |
|---|---|---|
| `SMTP_HOST` | (unset) | Without it nothing is sent, and the page says so. |
| `SMTP_PORT` | `587` | |
| `SMTP_USERNAME`, `SMTP_PASSWORD` | (unset) | Login, if the server needs one. |
| `SMTP_STARTTLS` | `true` | |
| `SMTP_FROM` | `SCIRM <no-reply@localhost>` | Use an address your mail service may send from (SPF/DKIM). |
| `PUBLIC_APP_URL` | (unset) | Link back to SCIRM in the email. |

In staging these come from the `scirm-secrets` keys `smtp-host`, `smtp-port`,
`smtp-username`, `smtp-password` and `smtp-from`. The keys are optional: without them the
pods still start.

**Development.** The Compose stack includes [Mailpit](https://mailpit.axllent.org/), which
catches every email. Read it at <http://127.0.0.1:8025>; nothing leaves your machine.

## Running

The coordinator checks for due reports every 30 seconds (`WEBHOOK_TICK_SECONDS`).
- **No double sends.** A due schedule is moved forward before it is sent (claimed with
  `FOR UPDATE SKIP LOCKED`), so several coordinator replicas never send it twice.
- **Failures.** A failed send (SMTP error, no member recipients left) is shown on the
  schedule, and the next run happens as normal.
