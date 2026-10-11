from aiogram import Router


def include_routers() -> Router:
	from . import backup, commands
	_router = Router()

	_router.include_router(commands.router)
	_router.include_router(backup.router)
	return _router

router = include_routers()
