"""
"""

from webkit_scraper import Node, NodeFactory, WebPageStub

from rpyc.utils.server import ThreadedServer
from rpyc import Service

import logging
logger = logging.getLogger(__name__)

def expose(*names, **kw):
    def decorate(Class):
        methods = dict( (name,getattr(Class,name)) for name in names )
        class Decorated(Class):
            def __init__(self, *args, **kwargs):
                kwargs.update(kw)
                super(Decorated, self).__init__(*args, **kwargs)
        for name,meth in methods.iteritems():
            setattr(Decorated, 'exposed_'+name, meth)
        return Decorated
    return decorate


@expose(
    'is_visible', 'set', 'get_bool_attr', 'drag_to', 'text', 'is_attached', 'eval_script', 'submit', 'path', 'click',
    'select_option', 'value', 'is_multi_select', 'set_attr', 'exec_script', 'is_selected', 'unselect_options',
    'tag_name', 'get_node_factory', 'is_checked', 'get_attr', 'is_disabled', 'xpath',
)
class _ExposedNode(Node):
    pass
class ExposedNode(_ExposedNode): pass

class ExposedNodeFactory(NodeFactory):
    _Node = ExposedNode

@expose(
    'body', 'reset', 'render', 'set_cookie', 'set_proxy', 'status_code', 'set_header', 'clear_proxy', 'url',
     'cookies', 'eval_script', 'wait', 'set_html', 'headers', 'exec_script', 'issue_node_cmd', 'visit', 'set_attribute',
     'source', 'clear_cookies', 'set_viewport_size', 'set_error_tolerant', 'reset_attribute', 'xpath',
    node_factory_class = ExposedNodeFactory
)
class _WebkitService(Service, WebPageStub):
    __name__ = 'MyName'
    def __init__(self, *args, **kwargs):
        node_factory_class = kwargs.pop('node_factory_class')
        Service.__init__(self, *args, **kwargs)
        WebPageStub.__init__(self, node_factory_class=node_factory_class)

    def on_connect(self):
        print('Client conected.')
    def on_disconnect(self):
        print('Client disconected. Stopping Webkit instance.')
        self.stop()
    def exposed_get_answer(self):
        return 42
class WebkitService(_WebkitService): pass

if __name__ == '__main__':

    logging.basicConfig(format='%(levelname)s:%(message)s',level=logging.INFO)
    t = ThreadedServer(WebkitService, port = 18861)
    t.start()
