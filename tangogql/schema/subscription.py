"""Module containing the Subscription implementation."""

import time
import asyncio
from collections import defaultdict

from graphene import ObjectType, String, Float, Interface, Field, List

from tangogql.schema.types import ScalarTypes
from tangogql.listener import TaurusWebAttribute

from PyTango import AttributeProxy, EventType, DevFailed

class ChangeData(ObjectType):
    value = ScalarTypes()
    w_value = ScalarTypes()
    quality = String()
    time = Float()


class ConfigData(ObjectType):
    description = String()
    label = String()
    unit = String()
    format = String()
    data_format = String()
    data_type = String()


class Event(Interface):
    device = String()
    name = String()


class ChangeEvent(ObjectType, interfaces=[Event]):
    data = Field(ChangeData)


class ConfigEvent(ObjectType, interfaces=[Event]):
    data = Field(ConfigData)


# NOTE: Maybe we should agree on having the constants in capitals
# Contains subscribed attributes
change_listeners = {}
config_listeners = {}


class Subscription(ObjectType):
    change_event = Field(ChangeEvent, models=List(String))
    config_event = Field(ConfigEvent)
    
    unsub_config_event = String(models=List(String))
    unsub_change_event = String(models=List(String))

    # TODO: documentation missing
    async def resolve_change_event(self, info, models=[]):
        def change_event_from(attr_proxy, value):
            device_proxy = attr_proxy.get_device_proxy()

            data = ChangeData(
                value=value.value,
                w_value=value.w_value,
                quality=value.quality,
                time=value.time.totime(),
            )

            return ChangeEvent(
                device=device_proxy.name(),
                name=attr_proxy.name(),
                data=data,
            )

        subs = [] # For attributes where subscriptions is enabled
        poll = [] # For attributes which have to be explicitly read

        for model in models:
            proxy = AttributeProxy(model)
            try:
                event_id = proxy.subscribe_event(EventType.CHANGE_EVENT, 1)
                subs.append((proxy, event_id))
            except DevFailed:
                poll.append(proxy)

        try:
            while True:
                for proxy, event_id in subs:
                    for event in proxy.get_events(event_id):
                        value = event.attr_value
                        yield change_event_from(proxy, value)

                for proxy in poll:
                    value = proxy.read()
                    yield change_event_from(proxy, value)

                await asyncio.sleep(1.0)

        except StopAsyncIteration:
            for proxy, event_id in subs:
                proxy.unsubscribe_event(event_id)

    async def resolve_config_event(self, info, models=[]):
        keeper = EventKeeper()
        for attr in models:
            taurus_attr = TaurusWebAttribute(attr, keeper)
            config_listeners[attr] = taurus_attr

        while config_listeners:
            evt_list = []
            events = keeper.get()
            for event_type, data in events.items():
                for attr_name, value in data.items():
                    device, attr = attr_name.rsplit('/', 1)
                    if event_type == "CONFIG":
                        data = ConfigData(description=value['description'],
                                          label=value['label'],
                                          unit=value['unit'],
                                          format=value['format'],
                                          data_format=value['data_format'],
                                          data_type=value['data_type']    
                                    )
                        event = ConfigEvent(event_type=event_type,
                                            device=device,
                                            name=attr,
                                            data=data)
                        evt_list.append(event)
            if evt_list:
                yield evt_list
            await asyncio.sleep(1.0)

    # TODO: documentation missing
    async def resolve_unsub_change_event(self, info, models=[]):
        result = []
        if change_listeners:
            for attr in models:
                listener = change_listeners[attr]
                if listener:
                    listener.clear()
                    del change_listeners[attr]
                    result.append(attr)
            yield f"Unsubscribed: {result}"
        else:
            yield "No attribute to unsubscribe"

    async def resolve_unsub_config_event(self, info, models=[]):
        result = []
        if config_listeners:
            for attr in models:
                listener = config_listeners[attr]
                if listener:
                    listener.clear()
                    del config_listeners[attr]
                    result.append(attr)
            yield f"Unsubscribed: {result}"
        else:
            yield "No attribute to unsubscribe"


# Help class
class EventKeeper:
    """A simple wrapper that keeps the latest event values for
    each attribute."""

    def __init__(self):
        self._events = defaultdict(dict)
        self._timestamps = defaultdict(dict)
        self._latest = defaultdict(dict)

    def put(self, model, action, value):
        """Update a model"""
        self._events[action][model] = value
        self._timestamps[action][model] = time.time()

    def get(self):
        """Returns the latest accumulated events"""
        tmp, self._events = self._events, defaultdict(dict)
        for event_type, events in tmp.items():
            self._latest[event_type].update(events)
        return tmp
