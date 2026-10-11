# KiraBot 2.16.0 Build fix & HTTPS

- Dockerfile: OmniGet is optional and non-fatal (`deploy/install_omniget.sh`, `INSTALL_OMNIGET=0` by default). A missing release archive can no longer break `docker build`.
- `https.sh`: Let's Encrypt + nginx HTTPS for the Mini App/help pages. Does not read or write `.env`, never touches data volumes. Uses an auto-loaded `compose.override.yml`; only public Mini App routes are exposed, the admin panel stays private. `--dry-run`, `--remove`, `--staging`, auto-renewal with a renewal self-test.
- masturbate and alcohol modules untouched.
