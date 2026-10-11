from aiogram import Router


def get_include_routers() -> Router:
    """Assemble built-in routers plus optional plugins."""
    from . import alcohol, callbacks, chat_updates, commands, community, community_life, errors, fsm, mems, masturbate, memory_cmds, rp, suite
    from bot.plugins import get_plugin_router

    router = Router(name="root")
    # Error observer is attached early; feature routers stay specific and the broad
    # group-text RP handler remains last so it does not swallow newer commands.
    router.include_router(errors.router)
    router.include_router(rp.router)
    router.include_router(memory_cmds.router)
    router.include_router(commands.router)
    router.include_router(callbacks.router)
    router.include_router(fsm.router)
    router.include_router(mems.router)
    router.include_router(masturbate.router)
    router.include_router(alcohol.router)
    router.include_router(community.router)
    router.include_router(community_life.router)
    router.include_router(suite.router)
    router.include_router(get_plugin_router())
    router.include_router(chat_updates.router)
    return router
