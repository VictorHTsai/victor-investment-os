# DGE Dashboard

Static monitoring UI for Dynamic Game Engine V1.

## Local preview
Serve this directory with any static HTTP server. The UI reads `data/latest.json`.

## Data contract
A producer should publish the serialized DGE output plus optional `price`. Never put API keys in this directory or client-side JavaScript.

## Deployment
Cloudflare Pages can publish this directory directly. Recommended production architecture is GitHub as source of truth, a scheduled/server-side DGE producer, and Cloudflare Pages for the static monitor.

The committed `latest.json` is explicitly a DEMO snapshot. Do not interpret it as live market analysis.
