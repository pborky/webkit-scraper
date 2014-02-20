import dryscrape.mixins

class RemoteMixin(object):
    def __init__(self, remote):
        self._remote = remote
    def __getattr__(self, attr):
        try:
            remote = object.__getattribute__(self, '_remote')
            if hasattr(remote, 'exposed_'+attr):
                return getattr(remote, attr)
        except AttributeError: pass
        raise AttributeError('Not found: %s '% attr)
    def __setattr__(self, attr, value):
        try:
            object.__getattribute__(self, attr)
            remote = object.__getattribute__(self, '_remote')
            if hasattr(remote, 'exposed_'+attr):
                return setattr(remote, attr, value)
        except AttributeError: pass
        return object.__setattr__(self, attr, value)

class Node( RemoteMixin,
            dryscrape.mixins.SelectionMixin,
            dryscrape.mixins.AttributeMixin):
    """ Node implementation wrapping a ``webkit_server`` node. """
    def xpath(self, xpath):
        return [ Node(n) for n in self._remote.xpath(xpath) ]



class Driver( RemoteMixin,
              dryscrape.mixins.WaitMixin,
              dryscrape.mixins.HtmlParsingMixin):
    """ Driver implementation wrapping a ``webkit_server`` driver.

    Keyword arguments are passed through to the underlying ``webkit_server.Client``
    constructor. By default, `node_factory_class` is set to use the dryscrape
    node implementation. """
    def __init__(self, connection):
        super(Driver, self).__init__(connection.root)
        self.connection=connection
    def __del__(self):
        del self.connection
    def xpath(self, xpath):
        return [ Node(n) for n in self._remote.xpath(xpath) ]
