#!/usr/bin/python
###################################################################################
# Copyright (C) 2014, 2015, 2016, 2017, 2018 N4IRR
#
# Permission to use, copy, modify, and/or distribute this software for any
# purpose with or without fee is hereby granted, provided that the above
# copyright notice and this permission notice appear in all copies.
#
# THE SOFTWARE IS PROVIDED "AS IS" AND ISC DISCLAIMS ALL WARRANTIES WITH
# REGARD TO THIS SOFTWARE INCLUDING ALL IMPLIED WARRANTIES OF MERCHANTABILITY
# AND FITNESS.  IN NO EVENT SHALL ISC BE LIABLE FOR ANY SPECIAL, DIRECT,
# INDIRECT, OR CONSEQUENTIAL DAMAGES OR ANY DAMAGES WHATSOEVER RESULTING FROM
# LOSS OF USE, DATA OR PROFITS, WHETHER IN AN ACTION OF CONTRACT, NEGLIGENCE
# OR OTHER TORTIOUS ACTION, ARISING OUT OF OR IN CONNECTION WITH THE USE OR
# PERFORMANCE OF THIS SOFTWARE.
###################################################################################
#
# Modified by SP2oNG 2019,2020
# Modified by F4HWN 2020
#

from time import time, sleep, clock, localtime, strftime
from random import randint
import socket
import struct
import thread
import shlex
import pyaudio
import audioop
import OPi.GPIO as GPIO

'''
sudo apt-get update
sudo apt-get install python-dev git
git clone https://github.com/Jeremie-C/OrangePi.GPIO
cd /OrangePi.GPIO
sudo python setup.py install

https://github.com/Jeremie-C/OrangePi.GPIO/blob/master/example/pull_up_down.py
'''

GPIO.setboard(GPIO.ZERO)                                # Orange Pi Zero board
GPIO.setmode(GPIO.BCM)                                  # set up BOARD GPIO numbering
GPIO.setup(10, GPIO.IN, pull_up_down=GPIO.PUD_OFF)      # set GPIO 10 as INPUT

GPIO.setwarnings(False)
GPIO.setup(7, GPIO.OUT)                                 # set GPIO 7 as OUTPUT

ipAddress = "127.0.0.1"
port = 51234
outputDeviceIndex = 1

def rxAudioStream():
    global ipAddress
    global port
    global outputDeviceIndex

    print('Start audio thread')
    
    FORMAT = pyaudio.paInt16
    CHUNK = 160
    CHANNELS = 1
    RATE = 48000
    
    stream = p.open(format=FORMAT,
                    channels = CHANNELS,
                    rate = RATE,
                    output = True,
                    output_device_index = outputDeviceIndex,
                    frames_per_buffer = CHUNK
                    )
    
    udp = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    udp.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEPORT, 1)
    print port
    udp.bind(("", port))
    
    lastKey = -1
    start_time = time()
    call = ''
    tg = ''
    loss = '0.00%'
    rxslot = '0'
    state = None
    stream.start_stream()
    while True:
        soundData, addr = udp.recvfrom(1024)
        if addr[0] != ipAddress:
            ipAddress = addr[0]
        if (soundData[0:4] == 'USRP'):
            eye = soundData[0:4]
            seq, = struct.unpack(">i", soundData[4:8])
            memory, = struct.unpack(">i", soundData[8:12])
            keyup, = struct.unpack(">i", soundData[12:16])
            talkgroup, = struct.unpack(">i", soundData[16:20])
            type, = struct.unpack("i", soundData[20:24])
            mpxid, = struct.unpack(">i", soundData[24:28])
            reserved, = struct.unpack(">i", soundData[28:32])
            audio = soundData[32:]
            if (type == 0): # voice
                audio = soundData[32:]
                GPIO.output(7, 1)
                print "GPIO 7 is 1/HIGH/True"
                #print(eye, seq, memory, keyup, talkgroup, type, mpxid, reserved, audio, len(audio), len(soundData))
                if (len(audio) == 320):
                    if RATE == 48000:
                        (audio48, state) = audioop.ratecv(audio, 2, 1, 8000, 48000, state)
                        stream.write(bytes(audio48), 160 * 6)
                    else:
                        stream.write(audio, 160)
                if (keyup != lastKey):
#                    print('key' if keyup else 'unkey')
                    if keyup:
                        start_time = time()
                    if keyup == False:
                        print '{} {} {} {} {} {} {:.2f}s'.format(
                                                                    strftime(" %m/%d/%y", localtime(start_time)),
                                                                    strftime("%H:%M:%S", localtime(start_time)),
                                                                    call, rxslot, tg, loss, time() - start_time)
                    lastKey = keyup
            if (type == 2): #metadata
                audio = soundData[32:]
                GPIO.output(7, 1)
                print "GPIO 7 is 1/HIGH/True"
                if ord(audio[0]) == 8:
                    tg = (ord(audio[9]) << 16) + (ord(audio[10]) << 8) + ord(audio[11])
                    rxslot = ord(audio[12]);
                    call = audio[14:]

        else:
            print(soundData, len(soundData))
            GPIO.output(7, 0)
            print "GPIO 7 is 0/LOW/False"

    time.sleep(0.1)
    stream.stop_stream()
    stream.close()
    p.terminate()
    udp.close()

def txAudioStream():
    global ipAddress
    global port
    global outputDeviceIndex
    
    FORMAT = pyaudio.paInt16
    CHUNK = 960
    CHANNELS = 1
    RATE = 48000
    state = None

    stream = p.open(format=FORMAT,
                    channels = CHANNELS,
                    rate = RATE,
                    input = True,
                    input_device_index= outputDeviceIndex,
                    frames_per_buffer = CHUNK,
                    )
    udp = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    lastPtt = ptt
    seq = 0
    while True:
        try:
            if RATE == 48000:       # If we are reading at 48K we need to resample to 8K
                audio48 = stream.read(CHUNK, exception_on_overflow=False)
                (audio, state) = audioop.ratecv(audio48, 2, 1, 48000, 8000, state)
            else:
                audio = stream.read(CHUNK, exception_on_overflow=False)
            if ptt != lastPtt:
                usrp = 'USRP' + struct.pack('>iiiiiii',seq, 0, ptt, 0, 0, 0, 0)
                udp.sendto(usrp, (ipAddress, port))
                seq = seq + 1
                print 'PTT: {}'.format(ptt)
            lastPtt = ptt
            if ptt:
                usrp = 'USRP' + struct.pack('>iiiiiii',seq, 0, ptt, 0, 0, 0, 0) + audio
                udp.sendto(usrp, (ipAddress, port))
                print 'transmitting'
                seq = seq + 1
        except:
            print("overflow")

def _find_getch():
    try:
        import termios
    except ImportError:
        # Non-POSIX. Return msvcrt's (Windows') getch.
        import msvcrt
        return msvcrt.getch
    
    # POSIX system. Create and return a getch that manipulates the tty.
    import sys, tty
    def _getch():
        fd = sys.stdin.fileno()
        old_settings = termios.tcgetattr(fd)
        try:
            tty.setraw(fd)
            ch = sys.stdin.read(1)
        finally:
            termios.tcsetattr(fd, termios.TCSADRAIN, old_settings)
        return ch
    
    return _getch

ptt = False     # toggle this to transmit (left up to you)

p = pyaudio.PyAudio()
thread.start_new_thread( rxAudioStream, () )
thread.start_new_thread( txAudioStream, () )

##root.mainloop()
#getch = _find_getch()

while True:
    '''
    ch = getch()
    print 'PTT:', ptt, '\n'
    if ord(ch) == 32: # 32 is spacebar
        ptt = not ptt
    if ord(ch) == 101:  # 101 is 'e' character, like 'exit'
       exit(0)
    # ptt = ~ptt
    '''
    if GPIO.input(10):
        print "GPIO 10 is 1/HIGH/True - PTT ON"
        ptt = not ptt



