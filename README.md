# azureSQLtoCockroachDB
Here’s a drop-in **README.md** for the `azureSQLtoCockroachDB` folder you showed.

---

# EventHub → Azure Function → CockroachDB

This function consumes JSON messages from **Azure Event Hubs** and upserts them into **CockroachDB** using the Postgres wire protocol. It’s a lightweight alternative to running Kafka Connect.

## Repo layout

```
azureSQLtoCockroachDB/
├─ EventHubToCrdb/            # Function code (Python)
│  ├─ __init__.py
│  └─ function.json
├─ host.json                  # Function host config
├─ local.settings.json        # Local dev settings (not deployed)
├─ requirements.txt           # Python deps (azure-functions, psycopg)
├─ start_azurite.sh           # (optional) start Azurite for local AzureWebJobsStorage
├─ test_connectivity.sh       # (optional) helper for quick connection checks
└─ venv/                      # (optional) your local Python venv
```

## What it does

* Trigger: **Event Hub** (batch, `cardinality: many`)
* Parses each event’s JSON
* Maps camelCase → snake\_case (e.g., `accountId -> account_id`)
* `UPSERT`s into a `transaction` table in CockroachDB

> Table is created if missing (`CREATE TABLE IF NOT EXISTS ...`).

---

## Prerequisites

* **Python 3.10/3.11** and **pip**
* **Azure Functions Core Tools v4** (`func`)
* **Azure CLI** (`az`)
* An **Event Hub** (private or public)
* A **CockroachDB** endpoint (private or public) + CA cert if verifying TLS

> For private Event Hubs/CRDB: the Function App needs **VNet Integration** and **Private DNS** to resolve/connect.

---

## Configuration

The function uses the following **App Settings** (env vars):

* `EventHubName` – the event hub (entity) name, e.g. `app-events`
* `EventHubReader` – **entity-level Listen** connection string
* `CrdbUrl` – Postgres URL to CockroachDB
  `postgresql://<user>:<pass>@<host>:26257/<db>?sslmode=verify-full`
* `CrdbCaPem` – *(optional)* CA certificate **PEM** contents; if provided the function writes it to `/tmp/crdb-ca.crt` and appends `sslrootcert` automatically

### Local development (`local.settings.json`)

Example (do not commit secrets):

```json
{
  "IsEncrypted": false,
  "Values": {
    "AzureWebJobsStorage": "UseDevelopmentStorage=true",
    "FUNCTIONS_WORKER_RUNTIME": "python",

    "EventHubName": "app-events",
    "EventHubReader": "Endpoint=sb://<ns>.servicebus.windows.net/;SharedAccessKeyName=crdb-reader;SharedAccessKey=<key>;EntityPath=app-events",

    "CrdbUrl": "postgresql://<user>:<pass>@<lb_or_node_ip>:26257/defaultdb?sslmode=verify-full",
    "CrdbCaPem": "-----BEGIN CERTIFICATE-----\n...your CA PEM...\n-----END CERTIFICATE-----\n"
  }
}
```

If you don’t use Azurite, set `AzureWebJobsStorage` to a **real** Storage account connection string.

---

## Run locally

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

# optional: start Azurite (if your local.settings.json uses UseDevelopmentStorage=true)
./start_azurite.sh

# start the function host
func start
```

> Ensure your machine can reach the Event Hub (VPN/VNet if private) and the Cockroach endpoint.

---

## Deploy to Azure

### Option A — Core Tools publish

```bash
func azure functionapp publish <your-function-app-name>
```

### Option B — Zip deploy (no Core Tools needed on your host)

```bash
# from repo root (where host.json lives)
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt -t ./.python_packages/lib/site-packages
zip -r function.zip . -x ".venv/*" ".git/*"

az functionapp deployment source config-zip \
  -g <rg> -n <your-function-app-name> --src function.zip
```

Set app settings (once):

```bash
az functionapp config appsettings set -g <rg> -n <app> \
  --settings \
  FUNCTIONS_WORKER_RUNTIME=python \
  EventHubName=app-events \
  EventHubReader="<entity-level listen conn string>" \
  CrdbUrl="postgresql://<user>:<pass>@<host>:26257/defaultdb?sslmode=verify-full" \
  CrdbCaPem="$(cat /path/to/ca.crt)"
```

**Private networking note:** enable **VNet Integration** for the Function App and use Private DNS so it can resolve `<ns>.servicebus.windows.net` and your CRDB host.

---

## Brief: install Azure Functions Core Tools v4 via npm (Ansible)
NOTE:  This [github does an ansible install of Azure Functions](https://github.com/jphaugla/cockroachCloudTerraform)

If you install Core Tools on a Linux node via **npm** under **nvm**, keep installs on a large disk and make `func` available to non-interactive shells:

```yaml
# expects:
#  - login_username (e.g., adminuser)
#  - crdb_file_location (e.g., /mnt/data)
#  - nvm already installed and a default Node version set

- name: Install Azure Functions Core Tools v4 (npm)
  become: true
  become_user: "{{ login_username }}"
  shell: |
    set -euo pipefail
    export NVM_DIR="{{ crdb_file_location }}/nvm"
    . "$NVM_DIR/nvm.sh"
    # remove any npm prefix setting; nvm rejects it
    npm config delete prefix >/dev/null 2>&1 || true
    nvm use default --delete-prefix --silent
    npm install -g azure-functions-core-tools@4 --unsafe-perm=true
  args: { executable: /bin/bash }

# wrapper so 'func' works in systemd/cron without sourcing nvm
- name: Install func wrapper
  become: true
  copy:
    dest: /usr/local/bin/func
    mode: "0755"
    content: |
      #!/usr/bin/env bash
      set -euo pipefail
      export NVM_DIR="{{ crdb_file_location }}/nvm"
      [ -s "$NVM_DIR/nvm.sh" ] && . "$NVM_DIR/nvm.sh"
      nvm use default >/dev/null
      v="$(nvm current)"
      exec "$NVM_DIR/versions/node/$v/bin/func" "$@"
```

---

## Troubleshooting

* **`func: command not found`**
  Core Tools not installed, or PATH not set. Use the wrapper above or source `/etc/profile.d` snippets.

* **`AzureWebJobsStorage` required**
  Functions host needs a Storage account. Use Azurite for local (`UseDevelopmentStorage=true`) or a real Storage connection string.

* **Private Event Hub/CRDB**
  Ensure the Function App is VNet-integrated and private DNS resolves both endpoints.

* **`node: No such file or directory` when calling `func`**
  Use the wrapper script so the correct Node is selected via `nvm`.

---

## Data contract

The function expects JSON events with fields like:

```json
{
  "id": "uuid-or-key",
  "accountId": "abc",
  "amountType": "debit",
  "initialDate": "2025-08-30T12:34:56Z",
  "...": "..."
}
```

It maps to snake\_case and upserts into `transaction(id PRIMARY KEY, …)`.

---

## Security

* Treat connection strings as **secrets**. Use Azure App Settings/Key Vault.
* Enforce TLS with `sslmode=verify-full` and a pinned CA (`CrdbCaPem`).

---
