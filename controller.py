import json
import sys
from datetime import datetime, timedelta
import random
import paho.mqtt.client as mqtt
from PyQt5.QtWidgets import *
from PyQt5.QtGui import *
from PyQt5.QtCore import *
from mqtt_init import *
import sqlite3
import os
from typing import Optional, List
from langchain.llms.base import LLM
import g4f

from langchain.prompts import PromptTemplate
from langchain.chains import LLMChain

os.environ['CURL_CA_BUNDLE'] = ''


class EducationalLLM(LLM):

    @property
    def _llm_type(self) -> str:
        return "custom"

    def _call(self, prompt: str, stop: Optional[List[str]] = None) -> str:
        out = g4f.ChatCompletion.create(model='gpt-3.5-turbo',
                                        provider=g4f.Provider.DeepAi,
                                        stream=False,
                                        messages=[
                                            {"role": "user", "content": prompt}]
                                        )
        print(out)
        if stop:
            stop_indexes = (out.find(s) for s in stop if s in out)
            min_stop = min(stop_indexes, default=-1)
            if min_stop > -1:
                out = out[:min_stop]
        return out


llm = EducationalLLM()

prompt = PromptTemplate(
    input_variables=["input"],
    template="""\
there are 3 devices which can be controlled:
door
air-conditioner
water-heater

and there are 2 available actions:
start
stop

you should select one of the options, based on the following request:
{input}

you should output a json with 2 fields one for the device name and one for the action
return only the json nothing more!
    """,
)

chain = LLMChain(llm=llm, prompt=prompt)



global CONNECTED
CONNECTED = False
r = random.randrange(1, 10000000)
clientname = "IOT_client-Id-orian-" + str(r)

DEVICE_NAME = "controller"
publish_topic = 'pr/orian/{device}/action'
subscribe_topic = f'pr/orian/#'


class DATABASE_CON:
    def __init__(self):
        self.conn = sqlite3.connect('iot.db', check_same_thread=False)

        self.cursor = self.conn.cursor()

        self.cursor.execute('''
            CREATE TABLE IF NOT EXISTS actions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                datetime TEXT NOT NULL,
                status TEXT NOT NULL,
                message TEXT NOT NULL,
                device TEXT NOT NULL
            )
        ''')

    def insert(self, record):
        self.cursor.execute('INSERT INTO actions (datetime, status, message, device) VALUES (?, ?, ?, ?)',
                            record)

        # Commit the changes to the database
        self.conn.commit()

    def get_all_database(self):
        self.cursor.execute('SELECT * FROM actions')
        return self.cursor.fetchall()

    def close(self):
        self.cursor.close()
        self.conn.close()


db_conn = DATABASE_CON()

class Mqtt_client():

    def __init__(self):
        # broker IP adress:
        self.database = db_conn
        self.broker = ''
        self.topic = ''
        self.port = ''
        self.clientname = ''
        self.username = ''
        self.password = ''
        self.subscribeTopic = ''
        self.publishTopic = ''
        self.publishMessage = ''
        self.on_connected_to_form = ''

    # Setters and getters
    def set_on_connected_to_form(self, on_connected_to_form):
        self.on_connected_to_form = on_connected_to_form

    def get_broker(self):
        return self.broker

    def set_broker(self, value):
        self.broker = value

    def get_port(self):
        return self.port

    def set_port(self, value):
        self.port = value

    def get_clientName(self):
        return self.clientName

    def set_clientName(self, value):
        self.clientName = value

    def get_username(self):
        return self.username

    def set_username(self, value):
        self.username = value

    def get_password(self):
        return self.password

    def set_password(self, value):
        self.password = value

    def get_subscribeTopic(self):
        return self.subscribeTopic

    def set_subscribeTopic(self, value):
        self.subscribeTopic = value

    def get_publishTopic(self):
        return self.publishTopic

    def set_publishTopic(self, value):
        self.publishTopic = value

    def get_publishMessage(self):
        return self.publishMessage

    def set_publishMessage(self, value):
        self.publishMessage = value

    def on_log(self, client, userdata, level, buf):
        print("log: " + buf)

    def on_connect(self, client, userdata, flags, rc):
        global CONNECTED
        if rc == 0:
            print("connected OK")
            CONNECTED = True
            self.on_connected_to_form();
        else:
            print("Bad connection Returned code=", rc)

    def on_disconnect(self, client, userdata, flags, rc=0):
        CONNECTED = False
        print("DisConnected result code " + str(rc))

    def on_message(self, client, userdata, msg):
        topic = msg.topic
        if topic.endswith('action'):
            return

        m_decode = str(msg.payload.decode("utf-8", "ignore"))
        print("message from:" + topic, m_decode)
        message = json.loads(m_decode)

        current_datetime = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

        self.database.insert((current_datetime,
                              message.get('status', ''),
                              message.get('message', ''),
                              topic.split('/')[-2]
                              ))

        if 'sms' in topic:
            self.on_sms_message(message)

        if 'door' in topic:
            self.on_door_message(message)

    def on_door_message(self, msg):
        all_table = self.database.get_all_database()
        only_doors = filter(lambda x: x[4] == 'door',all_table)
        five_minutes_ago = datetime.now() - timedelta(minutes=5)
        only_last_five_minutes = filter(lambda x: five_minutes_ago < datetime.strptime(x[1], '%Y-%m-%d %H:%M:%S'), only_doors)
        if len(list(only_last_five_minutes)) > 5:
            self.publish_to(publish_topic.replace('{device}', 'sms'),
                            json.dumps({'message': 'this is you ? someone opening the door all the time'}))

        elif (msg['status'] == True):
            self.publish_to(publish_topic.replace('{device}', 'sms'),
                            json.dumps({'message': 'Do you want to start the air-condition ?'}))

    def on_sms_message(self, msg):
        llm_output = chain.run(msg['message'])
        message = json.loads(llm_output)

        self.publish_to(publish_topic.replace('{device}', message['device']),
                        json.dumps({'status': message['action'] == 'start'}))

    def connect_to(self):
        # Init paho mqtt client class
        self.client = mqtt.Client(client_id=self.clientname, clean_session=True)  # create new client instance
        self.client.on_connect = self.on_connect  # bind call back function
        self.client.on_disconnect = self.on_disconnect
        self.client.on_log = self.on_log
        self.client.on_message = self.on_message
        self.client.username_pw_set(self.username, self.password)
        print("Connecting to broker ", self.broker)
        self.client.connect(self.broker, self.port)  # connect to broker

    def disconnect_from(self):
        self.client.disconnect()

    def start_listening(self):
        self.client.loop_start()

    def stop_listening(self):
        self.client.loop_stop()

    def subscribe_to(self, topic):
        self.client.subscribe(topic, qos=1)

    def publish_to(self, topic, message):
        if CONNECTED:
            self.client.publish(topic, message, qos=1)
        else:
            print("Can't publish. Connecection should be established first")


class ConnectionDock(QDockWidget):
    """Main """

    def __init__(self, mc):
        QDockWidget.__init__(self)

        self.mc = mc
        self.mc.set_on_connected_to_form(self.on_connected)
        self.eHostInput = QLineEdit()
        self.eHostInput.setInputMask('999.999.999.999')
        self.eHostInput.setText(broker_ip)

        self.ePort = QLineEdit()
        self.ePort.setValidator(QIntValidator())
        self.ePort.setMaxLength(4)
        self.ePort.setText(broker_port)

        self.eClientID = QLineEdit()
        global clientname
        self.eClientID.setText(clientname)

        self.eUserName = QLineEdit()
        self.eUserName.setText(username)

        self.ePassword = QLineEdit()
        self.ePassword.setEchoMode(QLineEdit.Password)
        self.ePassword.setText(password)

        self.eKeepAlive = QLineEdit()
        self.eKeepAlive.setValidator(QIntValidator())
        self.eKeepAlive.setText("60")

        self.eSSL = QCheckBox()

        self.eCleanSession = QCheckBox()
        self.eCleanSession.setChecked(True)

        self.eConnectbtn = QPushButton("Enable/Connect", self)
        self.eConnectbtn.setToolTip("click me to connect")
        self.eConnectbtn.clicked.connect(self.on_device_connect)
        self.eConnectbtn.setStyleSheet("background-color: gray")

        formLayot = QFormLayout()
        formLayot.addRow("Open/Close", self.eConnectbtn)

        widget = QWidget(self)
        widget.setLayout(formLayot)
        self.setTitleBarWidget(widget)
        self.setWidget(widget)
        self.setWindowTitle("Connect")

    def on_connected(self):
        self.eConnectbtn.setStyleSheet("background-color: green")

    def on_device_connect(self):
        self.mc.set_broker(self.eHostInput.text())
        self.mc.set_port(int(self.ePort.text()))
        self.mc.set_clientName(self.eClientID.text())
        self.mc.set_username(self.eUserName.text())
        self.mc.set_password(self.ePassword.text())
        self.mc.connect_to()
        self.mc.start_listening()
        self.mc.subscribe_to(subscribe_topic)


class MainWindow(QMainWindow):

    def __init__(self, parent=None):
        QMainWindow.__init__(self, parent)

        # Init of Mqtt_client class
        self.mc = Mqtt_client()

        # general GUI settings
        self.setUnifiedTitleAndToolBarOnMac(True)

        # set up main window
        self.setGeometry(30, 100, 300, 150)
        self.setWindowTitle(DEVICE_NAME.upper())

        # Init QDockWidget objects
        self.connectionDock = ConnectionDock(self.mc)

        self.addDockWidget(Qt.TopDockWidgetArea, self.connectionDock)


app = QApplication(sys.argv)
mainwin = MainWindow()
mainwin.show()
app.exec_()
