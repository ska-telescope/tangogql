#!/usr/bin/env python3

import asyncio
from aiohttp import web

import json
import jwt
import os

from graphql_ws.aiohttp import AiohttpSubscriptionServer
from graphql import format_error
from graphql.execution.executors.asyncio import AsyncioExecutor

from tangogql.schema.tango import tangoschema
from tangogql.auth import AuthorizationMiddleware, AuthenticationMiddleware, AuthError

from tangogql.schema.errors import ErrorParser

subscription_server = AiohttpSubscriptionServer(tangoschema)
routes = web.RouteTableDef()

# FIXME: aiohttp doesn't support automatic serving of index files when serving
#        directories statically, so we need to define a number of routes to
#        serve the GraphiQL interface. Is there a better way?
@routes.get('/graphiql')
async def graphiql_noslash(request):
    return web.HTTPFound('/graphiql/')


@routes.get('/graphiql/')
async def graphiql(request):
    return web.FileResponse("./static/graphiql/index.html")

routes.static('/graphiql/css', 'static/graphiql/css')
routes.static('/graphiql/js', 'static/graphiql/js')



@routes.post("/db")
async def db_handler(request):
    """Serve GraphQL queries."""
    loop = asyncio.get_event_loop()
    payload = await request.json()
    query = payload.get("query")
    variables = payload.get("variables")
    context = _build_context(request)

    # Spawn query as a coroutine using asynchronous executor
    response = await tangoschema.execute(
        query,
        variable_values=variables,
        middleware=[AuthorizationMiddleware, AuthenticationMiddleware],
        context_value=context,
        return_promise=True,
        executor=AsyncioExecutor(loop=loop),
    )
    data = {}
    if response.errors:
        for e in response.errors:
            if hasattr(e,"original_error"):
                if isinstance(e.original_error, AuthError):
                    return web.HTTPUnauthorized()    
        parsed_errors = [ErrorParser.parse(e) for e in(response.errors)]
        if parsed_errors:
            data['errors'] = ErrorParser.remove_duplicated_errors(parsed_errors)
    if response.data:
        data["data"] = response.data
    jsondata = json.dumps(data)

    return web.Response(
        text=jsondata, headers={"Content-Type": "application/json"}
    )


@routes.get("/socket")
async def socket_handler(request):
    ws = web.WebSocketResponse(protocols=("graphql-ws",))
    await ws.prepare(request)
    await subscription_server.handle(ws)
    return ws


class ClientInfo:
    def __init__(self, user, groups):
        if user is not None and type(user) is not str:
            raise TypeError("user must be a string or None")

        if not type(groups) is list:
            raise TypeError("groups must be a list")

        self.user = user
        self.groups = groups


def _build_context(request):
    config = request.app["config"]

    try:
        token = request.cookies.get("webjive_jwt", "")
        claims = jwt.decode(token, config.secret)
    except jwt.InvalidTokenError:
        claims = {}

    user = claims.get("username")
    groups = claims.get("groups", [])

    return {
        "client": ClientInfo(user, groups),
        "config": config
    }
