import dryscrape.mixins

class ConnectionError(Exception):
    pass

class DiscoveryError(Exception):
    pass

class RemoteMixin(object):
    def __init__(self, remote, connection):
        self._remote = remote
        self._connection = connection
    def __del__(self):
        del self._connection
    def __getattr__(self, attr):
        try:
            conn = object.__getattribute__(self, '_connection')
            if attr=='_connection':
                return conn
            if not conn.closed:
                remote = object.__getattribute__(self, '_remote')
                if attr == '_remote':
                    return remote
                if hasattr(remote, 'exposed_'+attr):
                    return getattr(remote, attr)
            else:
                raise ConnectionError('Connection closed.')
        except AttributeError:
            pass
        raise AttributeError('Not found: %s '% attr)
    def __setattr__(self, attr, value):
        try:
            object.__getattribute__(self, attr)
            conn = object.__getattribute__(self, '_connection')
            if not conn.closed:
                remote = object.__getattribute__(self, '_remote')
                if hasattr(remote, 'exposed_'+attr):
                    return setattr(remote, attr, value)
            else:
                raise ConnectionError('Connection closed.')
        except AttributeError: pass
        return object.__setattr__(self, attr, value)

class Node( RemoteMixin,
            dryscrape.mixins.SelectionMixin,
            dryscrape.mixins.AttributeMixin):
    """ Node implementation wrapping a ``webkit_server`` node. """
    def xpath(self, xpath):
        return [ Node(n, self._connection) for n in self._remote.xpath(xpath) ]



class Driver( RemoteMixin,
              dryscrape.mixins.WaitMixin,
              dryscrape.mixins.HtmlParsingMixin):
    """ Driver implementation wrapping a ``webkit_server`` driver.

    Keyword arguments are passed through to the underlying ``webkit_server.Client``
    constructor. By default, `node_factory_class` is set to use the dryscrape
    node implementation. """
    def __init__(self, connection):
        super(Driver, self).__init__(connection.root, connection)
    def xpath(self, xpath):
        return [ Node(n, self._connection) for n in self._remote.xpath(xpath) ]

class Discovery:
    def __init__(self, host, port):
        self.host = host
        self.port = port
        self.discoverer = None
    def discover(self, service):
        import rpyc
        if self.discoverer is None or self.discoverer.closed:
            try:
                self.discoverer = rpyc.connect(self.host, self.port)
            except:
                raise DiscoveryError('Discovery service not found.')
        host = self.discoverer.root.discover(service)
        if host is not None:
            return rpyc.connect(*host)
        else:
            raise DiscoveryError('Service discovery failed.')
    def driver(self, service):
        return Driver(self.discover(service))