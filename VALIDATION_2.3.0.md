# Validation 2.3.0

- `python3 -m compileall -q bot`: PASS.
- Protected modules `bot/handlers/masturbate/*.py` and `bot/handlers/alcohol/*.py`: SHA-256 unchanged from 2.2.0.
- Full pytest could not be executed in the artifact environment because runtime dependencies `aiogram` and `aiosqlite` are not installed there. Run the included project tests in the Docker image/server environment before production cutover.
- Database migration is deliberately implemented as an explicit pre-deploy script (`upgrade_2_3.sh`) and never deletes old Docker volumes.
