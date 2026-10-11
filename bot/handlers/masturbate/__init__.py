from aiogram import Router


def include_routers() -> Router:
    from . import callbacks, commands

    _router = Router()
    _router.include_router(commands.router)
    _router.include_router(callbacks.router)
    return _router

router = include_routers()
