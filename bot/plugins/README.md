# KiraBot plugins

Drop a Python file into this folder and expose either:

```python
from aiogram import Router
router = Router()
```

or a `setup(router: Router)` function. Plugin failures are isolated and logged.
