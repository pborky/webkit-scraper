"""
Example client.
"""
from webkit_scraper.driver import Discovery

DISCOVERY_HOST = 'localhost'
DISCOVERY_PORT = 18811
DISCOVERY_PATH = '/tmp/webkit_service/18811'
SERVICE_NAME = 'WEBKIT'

discovery = Discovery(path=DISCOVERY_PATH)
c = discovery.driver(SERVICE_NAME)
USER_AGENT = 'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chromium/28.0.1500.71 Chrome/28.0.1500.71 '
ACCEPT_LANG = 'en-US,en;q=0.8'
ACCEPT = 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8'
c.set_header('user-agent',USER_AGENT)
c.set_header('accept-language', ACCEPT_LANG)
c.set_header('accept', ACCEPT)
c.set_error_tolerant(True)
c.set_attribute('auto_load_images', False)
c.set_attribute('plugins_enabled', False)
c.clear_cookies()
c.visit('http://search.yahoo.com/')
c.wait()
n = c.at_xpath('//input[@name="p"]')
n.set('webkit scraper')
f = n.form()
f.submit()
for i in range(5):
  print '\n'.join('%s (%s)' %(n.text(), n.get_attr('href')) for n in c.xpath('//ol/li//h3/a'))
  n = c.at_xpath('//div[@id="pg"]/a[@id="pg-next"]')
  n.click()
