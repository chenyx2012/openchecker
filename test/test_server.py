# -*- coding: utf-8 -*-
from concurrent.futures import ThreadPoolExecutor
import json
import logging
import tornado.web
import tornado.ioloop
import tornado.httpserver
import tornado.options 
from tornado import gen

from datetime import datetime, timedelta
exitFlag = 0
class Main(tornado.web.RequestHandler):
    executor = ThreadPoolExecutor(1000)

    @gen.coroutine
    def get(self):
        """get request"""
        self.set_header('Content-Type', 'application/json; charset=UTF-8')
        data = json.loads(self.request.body)
        print(data)

    @gen.coroutine
    def post(self):
        '''post request'''
        self.set_header('Content-Type', 'application/json; charset=UTF-8')
        data = json.loads(self.request.body)
        print(data)
    

application = tornado.web.Application([(r"/callback", Main)])

if __name__ == '__main__':
    httpServer = tornado.httpserver.HTTPServer(application)
    port = 8898
    httpServer.bind(port)   
    httpServer.start(1)
    logging.info(f"Server started successfully on port {port}")
    tornado.ioloop.IOLoop.current().start()
    
