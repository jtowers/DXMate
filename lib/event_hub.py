from .util import *

class EventHub(object):
	event_hooks = dict()

	@classmethod
	def subscribe(self, event_name, cb):
		if event_name in self.event_hooks.keys():
			self.event_hooks[event_name].append(cb)
		else:
			self.event_hooks[event_name] = [cb];

	@classmethod
	def publish(self, event_name, *args):
		if event_name in self.event_hooks.keys():
			for cb in self.event_hooks[event_name]:
				cb(*args)
