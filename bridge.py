#!/usr/bin/python
import serial
import json
import time
import os
import sys
import logging
from logging.handlers import RotatingFileHandler
import traceback
import threading

logger = logging.getLogger("bridge")
logger.level = logging.DEBUG
# 2 M
LOG_SIZE = 2 * 1024 * 1024

class ModemBridge():
    def __init__(self, port1, baud1, port2, baud2):
        self.serial1 = serial.Serial()
        self.serial1.baudrate = baud1
        self.serial1.port = port1
        self.serial1.timeout = 1
        self.serial2 = serial.Serial()
        self.serial2.baudrate = baud2
        self.serial2.port = port2
        self.serial2.timeout = 1
        self.is_running = False
        self.discon_lock = threading.Lock()
    
    def rxtx(self, rx, tx):
        try:
            while self.is_running:
                while rx.in_waiting > 0:
                    data = rx.read(rx.in_waiting)
                    tx.write(data)
                time.sleep(0.1)
        except serial.SerialException as e:
            logger.error("bridge port error: {}".format(e))

        self.is_running = False
        self.disconnect()
    
    def connect(self):
        try:
            logger.info("Starting bridge {}@{} <-> {}@{}".format(self.serial1.port, self.serial1.baudrate, self.serial2.port, self.serial2.baudrate))
            self.serial1.open()
            self.serial2.open()
            # create lock file
            #if self.lockfile is not None:
            #    os.system("touch {}".format(self.lockfile))
            # start threads
            self.is_running = True
            thread_a = threading.Thread(target=self.rxtx, args=(self.serial1, self.serial2))
            thread_a.setDaemon(True)
            thread_a.start()
            thread_b = threading.Thread(target=self.rxtx, args=(self.serial2, self.serial1))
            thread_b.setDaemon(True)
            thread_b.start()
            return True
        except serial.SerialException:
            logger.error("Failed to open serial port")
            return False
        pass

    def disconnect(self):
        self.discon_lock.acquire()
        # delete lock file
        #if self.lockfile is not None:
        #    os.system("rm {}".format(self.lockfile))
        if self.serial1.is_open:
            self.serial1.close()
            logger.info("Closed bridge port {}".format(self.serial1.port))
        if self.serial2.is_open:
            self.serial2.close()
            logger.info("Closed bridge port {}".format(self.serial2.port))
        self.discon_lock.release()

def main():
    # read config file
    config = json.load(open('config.json'))
    src_port = config['Source']['Port']
    src_baud = config['Source']['Baudrate']
    dst_port = config['Destination']['Port']
    dst_baud = config['Destination']['Baudrate']
    
    #stdout = True
    #if 'StdOut' in config:
    #    stdout = config['StdOut']
    # set up logger
    #os.makedirs(config['LogsFolder'], exist_ok=True)
    #log_format = '%(asctime)s %(levelname)s: %(message)s'
    #log_handlers = [RotatingFileHandler(config['LogsFolder'] + '/bridge.log', maxBytes=LOG_SIZE, backupCount=5)]
    #if stdout:
    #    log_handlers.append(logging.StreamHandler(sys.stdout))
    #logging.basicConfig(format=log_format,
    #                    level=logging.INFO,
    #                    handlers=log_handlers)
    logger.info("< < < Bridge service started > > >")
    global connected
    connected = True
    
    # create bridges
    bridge = ModemBridge(src_port, src_baud, dst_port, dst_baud)
    if not bridge.connect():
        logger.warning("Modem bridge not started")

    # wait until the service gets killed
    while bridge.is_running:
        time.sleep(0.5)

    logger.error("Bridge service stopped")
    connected = False
    #logger.error("Bridge service stopped, waiting 5 seconds...")
    #time.sleep(5)   # delay for restart from systemd to wait for /dev/tty to appear

def bridge():
    try:
        main()
    except Exception as e:
        logger.error("Unhandled exception: {}".format(e))
        logger.error(traceback.format_exc())

if __name__ == '__main__':
    bridge()