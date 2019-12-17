import logging
import json
import os.path
import uuid
from datetime import datetime, timedelta

import requests
import tornado.escape
import tornado.ioloop
import tornado.options
import tornado.web
import tornado.websocket

import settings as st


class Application(tornado.web.Application):
    def __init__(self):
        handlers = [
            (r"/", BeerHandler),
            (r"/beersocket", BeerSocketHandler),
            (r"/record", RecordHandler),
            (r"/report", ReportHandler),
            (r"/history", HistoryHandler),
        ]
        settings = dict(
            template_path=os.path.join(os.path.dirname(__file__), "templates"),
            static_path=os.path.join(os.path.dirname(__file__), "static"),
            xsrf_cookies=True,
        )
        super(Application, self).__init__(handlers, **settings)


class BeerHandler(tornado.web.RequestHandler):
    def get(self):
        self.render("index.html", messages=BeerSocketHandler.cache)


class BeerSocketHandler(tornado.websocket.WebSocketHandler):
    waiters = set()
    cache = []
    cache_size = 200

    def get_compression_options(self):
        return {}

    def open(self):
        BeerSocketHandler.waiters.add(self)

    def on_close(self):
        BeerSocketHandler.waiters.remove(self)

    @classmethod
    def update_cache(cls, chat):
        cls.cache.append(chat)
        if len(cls.cache) > cls.cache_size:
            cls.cache = cls.cache[-cls.cache_size:]

    @classmethod
    def send_updates(cls, chat):
        logging.info("sending message to %d waiters", len(cls.waiters))
        for waiter in cls.waiters:
            try:
                waiter.write_message(chat)
            except Exception as e:
                logging.error(str(e), exc_info=True)

    def on_message(self, message):
        logging.info("got message %r", message)
        beer_record = tornado.escape.json_decode(message)
        record = {"id": str(uuid.uuid4()), "body": json.dumps(beer_record)}
        record["html"] = tornado.escape.to_basestring(
            self.render_string("new_record.html", message=record)
        )

        BeerSocketHandler.update_cache(record)
        BeerSocketHandler.send_updates(record)


class RecordHandler(tornado.web.RequestHandler):

    def get(self):
        self.render("insert_record.html")

    def post(self):
        beer_type = self.get_argument("BeerType")
        total_ml = self.get_argument("TotalML")
        date = self.get_argument("Date")

        data = {
            "BeerType": beer_type,
            "TotalML": total_ml,
            "Date": date
        }
        response = requests.post(st.BEER_SERVER_HOST + st.BEERS_URL, data=data)
        if response.status_code != 200:
            self.write(response.reason)

        self.redirect("/record")


class ReportHandler(tornado.web.RequestHandler):

    def get(self):
        date = datetime.now().date().isoformat()
        response = requests.get(st.BEER_SERVER_HOST + st.REPORT_URL, params={'date': date})
        report = json.loads(response.content)
        self.render("report.html", **report)


class HistoryHandler(tornado.web.RequestHandler):

    def get(self):
        begin_date = (datetime.now() - timedelta(days=30)).date().isoformat()
        end_date = datetime.now().date().isoformat()
        params = {
            'beginDate': begin_date,
            'endDate': end_date
        }
        response = requests.get(st.BEER_SERVER_HOST + st.BEERS_URL, params=params)
        history = json.loads(response.content)
        self.render("history.html", history=history)


def main():
    app = Application()
    app.listen(3001)
    tornado.ioloop.IOLoop.current().start()


if __name__ == "__main__":
    main()
