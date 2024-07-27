from flask import Flask
import json

from views.mapping import mapping
from views.kneeboard import kneeboard

app = Flask(__name__)
app.config.from_file('config.json', load=json.load)

app.register_blueprint(mapping)
app.register_blueprint(kneeboard)

if __name__ == '__main__':
    app.run(debug=True, port=9292)
