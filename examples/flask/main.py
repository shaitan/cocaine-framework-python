#!/usr/bin/env python

from cocaine.worker import Worker
from cocaine.services import Service
from cocaine.decorators.wsgi import wsgi

from app import NAMESPACE
from app import KEY
from app import app

storage = Service("storage")


def write(request, response):
    data = yield request.read()
    try:
        yield storage.write(NAMESPACE, KEY, data, [])
        response.write("Ok")
    except Exception as err:
        response.error(-100, repr(err))
    finally:
        response.close()


def read(request, response):
    try:
        data = yield storage.read(NAMESPACE, KEY)
        response.write(data)
    except Exception as err:
        response.error(-100, repr(err))
    finally:
        response.close()


if __name__ == '__main__':
    W = Worker()
    W.run({"write": write,
           "read": read,
           "http": wsgi(app)})
