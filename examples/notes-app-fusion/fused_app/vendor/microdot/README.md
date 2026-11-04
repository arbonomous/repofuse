# Microdot

[![tests](https://code.miguelgrinberg.com/miguelgrinberg/microdot/badges/workflows/tests.yml/badge.svg)](https://code.miguelgrinberg.com/miguelgrinberg/microdot/actions)

*“The impossibly small web framework for Python and MicroPython”*

Microdot is a minimalistic Python web framework inspired by Flask. Given its
small size, it can run on systems with limited resources such as
microcontrollers. Both standard Python (CPython) and MicroPython are supported.

```python
from microdot import Microdot

app = Microdot()

@app.route('/')
async def index(request):
    return 'Hello, world!'

app.run()
```

## Resources

- [git](https://code.miguelgrinberg.com/miguelgrinberg/microdot)
- [Change Log](https://code.miguelgrinberg.com/miguelgrinberg/microdot/src/branch/main/CHANGES.md)
- [Documentation](https://microdot.readthedocs.io/)
- [PyPI](https://pypi.python.org/pypi/microdot)
- [Contributor's guide](CONTRIBUTING.md)
- [Security policy](SECURITY.md)

The following links are for legacy version 1 of Microdot:

- [git](https://github.com/miguelgrinberg/microdot/tree/v1)
- [Documentation](https://microdot.readthedocs.io/en/v1/)

Note that version 1 is no longer maintained, so you should consider migrating
to version 2. See the
[migration notes](https://microdot.readthedocs.io/en/latest/implementation/migrating.html)
for help.

## Roadmap

The following features are planned for future releases of Microdot, both for
MicroPython and CPython:

- Authentication support, similar to [Flask-Login](https://github.com/maxcountryman/flask-login) for Flask (**Added in version 2.1**)
- Support for forms encoded in `multipart/form-data` format (**Added in version 2.2**)
- CSRF protection extension (**Added in version 2.5**)
- Type hints (**Added in version 2.6**)
- Pub/sub mini-framework for WebSocket and SSE
- OpenAPI integration, similar to [APIFairy](https://github.com/miguelgrinberg/apifairy) for Flask

Do you have other ideas to propose? Let's [discuss them](https://github.com/:miguelgrinberg/microdot/discussions/new?category=ideas)!

Sponsor this project
--------------------

This project relies on contributions from its users. If you benefit from it please consider making a single or ongoing monetary contribution in one of the following platforms:

- [Github Sponsors](https://github.com/sponsors/miguelgrinberg)
- [Patreon](https://patreon.com/miguelgrinberg)
- [Buy me a Coffee](https://buymeacoffee.com/miguelgrinberg)
- [thanks.dev](https://thanks.dev/u/gh/miguelgrinberg)
- [PayPal](https://paypal.me/miguelgrinberg)

Thank you!
