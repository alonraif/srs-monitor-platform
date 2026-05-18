Place TLS certificate files here for Nginx proxy services:

- fullchain.pem
- privkey.pem

If either file is missing, the proxy entrypoint auto-generates a self-signed
certificate on startup (default CN: `localhost`, default validity: 365 days).

Optional environment variables for proxy services:

- SELF_SIGNED_CERT_CN (default: `localhost`)
- SELF_SIGNED_CERT_DAYS (default: `365`)

Do not commit real private keys to version control.
