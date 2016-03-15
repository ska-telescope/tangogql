from asyncio import QueueFull
import numpy as np
from taurus import Attribute, Manager
from taurus.core.taurusbasetypes import TaurusEventType
import PyTango

# Manager().changeDefaultPollingPeriod(1000)


def error_str(err):
    if isinstance(err, PyTango.DevFailed):
        err = err[0]
        return "[{0}] {1}".format(err.reason, err.desc)
    return str(err)


def format_value(value, attr_type):
    if attr_type is PyTango.ArgType.DevState:
        return str(value)
    if isinstance(value, np.ndarray):
        return value.tobytes()  # TODO: is this a copy..?
    return value


def format_value_event(evt):
    return {
        "value": format_value(evt.value, evt.type),
        "w_value": format_value(evt.w_value, evt.type),
        "quality": str(evt.quality),
        "time": evt.time.totime()
    }


def format_config_event(evt):
    return {
        'description': evt.description,
        'label': evt.label,
        'unit': evt.unit if evt.unit != "No unit" else "",
        'format': evt.format,
        # ...
    }


# Based on code from the taurus-web project
class TaurusWebAttribute(object):

    def __init__(self, name, queue):
        self.name = name
        self.queue = queue
        self._last_time = 0
        self.last_value_event = None
        self.last_config_event = None
        self.attribute = Attribute(self.name)
        self.attribute.addListener(self)

    def eventReceived(self, evt_src, evt_type, evt_value):

        if evt_type == TaurusEventType.Error:
            action = "ERROR"
            value = error_str(evt_value)
        else:
            if evt_type == TaurusEventType.Config:
                action = "CONFIG"
                value = format_config_event(evt_src)
                self.last_config_event = value
            else:
                self._last_time = evt_value.time.tv_sec
                action = "CHANGE"
                value = format_value_event(evt_value)
                self.last_value_event = value

        # self.callback(self.name, {"type": action, "data": {self.name: value}})
        event = {"type": action, "data": {self.name: value}}
        try:
            self.queue.put_nowait(event)
        except QueueFull:
            print("Queue full!")
        print(event)

    def clear(self):
        self.attribute.removeListener(self)
