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

def parse_sxrat(cmd):
    try:
        cmd_str = cmd.decode("utf-8")
        sxrat = cmd_str.replace("AT^SXRAT=", "").strip()
        return sxrat
    except UnicodeDecodeError:
        return "0,0"

def parse_ceer(resp):
    try:
        resp_str = resp.decode("utf-8")
        ceer = resp_str.replace("+CEER:", "").replace("OK", "").strip()
        return ceer
    except UnicodeDecodeError:
        return ""


class ModemBridge():
    def __init__(self, src_port, src_baud, dst_port, dst_baud):
        self.src_serial = serial.Serial()
        self.src_serial.baudrate = src_baud
        self.src_serial.port = src_port
        self.src_serial.timeout = 1
        self.dst_serial = serial.Serial()
        self.dst_serial.baudrate = dst_baud
        self.dst_serial.port = dst_port
        self.dst_serial.timeout = 1
        self.is_running = False
        #self.discon_lock = threading.Lock()
    
    def loop(self, src, dst):
        try:
            sxrat = "0,0"

            while self.is_running:
                # receive command
                cmd = bytes()
                while not cmd.endswith(b"\r\n"):
                    # read next byte(s)
                    if src.in_waiting > 0:
                        cmd += src.read(src.in_waiting)
                    else:
                        time.sleep(0.1)
                logger.debug("Read command [{}]: {}".format(self.src_serial.port, cmd))
                cmd = cmd.replace(b"at", b"AT")
                
                # process command
                ignore = False
                send_cmd = cmd
                if cmd.startswith(b"AT"):
                    if cmd.startswith((b"AT+", b"ATI", b"ATV")):
                        send_cmd = cmd
                    elif cmd.startswith(b"AT^SCTM?"):
                        send_cmd = b"AT#TEMPMON?"
                    elif cmd.startswith(b"AT^SXRAT="):
                        ignore = True
                        sxrat = parse_sxrat(cmd)
                    elif cmd.startswith(b"AT^SXRAT?"):
                        ignore = True
                    elif cmd.startswith(b"AT^SCFG="):
                        ignore = True
                    elif cmd.startswith(b"AT^SPOW="):
                        ignore = True
                         
                if not ignore:
                    logger.debug("Send command [{}]: {}".format(self.dst_serial.port, send_cmd))
                    dst.write(send_cmd)

                # receive response
                resp = bytes()
                if not ignore:
                    while not resp.endswith((b"OK\r\n", b"ERROR\r\n")):
                        # read next byte(s)
                        if dst.in_waiting > 0:
                            resp += dst.read(dst.in_waiting)
                        else:
                            time.sleep(0.1)
                    logger.debug("Read response [{}]: {}".format(self.dst_serial.port, resp))
                    
                # process response
                send_resp = resp
                if ignore:
                    send_resp = b"\r\nOK\r\n"
                if cmd.startswith(b"AT^SXRAT?"):
                    send_resp = ("\r\n^SXRAT: {}\r\n\r\nOK\r\n".format(sxrat)).encode("utf-8")
                elif cmd.startswith(b"AT+CEER"):
                    ceer = parse_ceer(resp)
                    send_resp = ("\r\n+CEER: \"{}\"\r\n\r\nOK\r\n".format(ceer)).encode("utf-8")
                
                logger.debug("Send response [{}]: {}".format(self.src_serial.port, send_resp))
                src.write(send_resp)

                # sleep, repeat
                time.sleep(0.1)
    
        except serial.SerialException as e:
            logger.error("bridge port error: {}".format(e))
        finally:
            self.is_running = False
            self.disconnect()
    
    def convert_at_command(self, cmd=""):
        if cmd.startswith("AT"):
            if cmd.startswith("AT+") or cmd.startswith("ATI") or cmd.startswith("ATV"):
                return cmd
        else:
            return cmd

    def connect(self):
        try:
            logger.info("Starting bridge {}@{} -> {}@{}".format(self.src_serial.port, self.src_serial.baudrate, self.dst_serial.port, self.dst_serial.baudrate))
            self.src_serial.open()
            self.dst_serial.open()
            self.src_serial.reset_input_buffer()
            self.dst_serial.reset_input_buffer()
            # create lock file
            #if self.lockfile is not None:
            #    os.system("touch {}".format(self.lockfile))
            # start threads
            self.is_running = True
            thread_a = threading.Thread(target=self.loop, args=(self.src_serial, self.dst_serial))
            thread_a.setDaemon(True)
            thread_a.start()
            return True
        except serial.SerialException:
            logger.error("Failed to open serial port")
            return False
        pass

    def disconnect(self):
        #self.discon_lock.acquire()
        # delete lock file
        #if self.lockfile is not None:
        #    os.system("rm {}".format(self.lockfile))
        if self.src_serial.is_open:
            self.src_serial.close()
            logger.info("Closed bridge port {}".format(self.src_serial.port))
        if self.dst_serial.is_open:
            self.dst_serial.close()
            logger.info("Closed bridge port {}".format(self.dst_serial.port))
        #self.discon_lock.release()

def main():
    # read config file
    config = json.load(open('config.json'))
    src_port = config['Source']['Port']
    src_baud = config['Source']['Baudrate']
    dst_port = config['Destination']['Port']
    dst_baud = config['Destination']['Baudrate']
    
    stdout = True
    if 'StdOut' in config:
        stdout = config['StdOut']
    # set up logger
    #os.makedirs(config['LogsFolder'], exist_ok=True)
    log_format = '%(asctime)s %(levelname)s: %(message)s'
    log_handlers = [RotatingFileHandler('bridge.log', maxBytes=LOG_SIZE, backupCount=5)]
    if stdout:
        log_handlers.append(logging.StreamHandler(sys.stdout))
    logging.basicConfig(format=log_format,
                        level=logging.INFO,
                        handlers=log_handlers)
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