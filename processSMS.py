#!/usr/bin/env python

"""\
MC Modem Handler

Objectives:
1) Forward SMS to active destination number
2) Forward calls to active destinatino number (using USSD)
3) Listen for keywords to update active destination number

Obj1: Stores two types of destination number: duty number (gets all sms & calls), and supervisor number (subscribes to keywords or all sms).

Obj2: When destination number is updated, use USSD code to update call divert status.

Obj3: Support for keywords: "Takeover duty", "Sub <keyword>", "Unsub <keyword>", "Silence", "Alert", "Status", "Help"

Obj4: Poll a job folder for message. Sends them out where: first line contains destination, second line contains message
"""

from __future__ import print_function

import logging, time, os

PORT = '/dev/ttyUSB2'
BAUDRATE = 115200
PIN = None # SIM card PIN (if any)
DUTYNUM = ''
SUPERVISORNUM = []
STAFFNUM = []
SILENTNUM = []
POLLPATH = '/var/www/jobs/'
DESTPATH = '/root/mcmodem/completed/'
#SingTel Hi
#SMSC_NUM = '+6596400001'
#M1
SMSC_NUM = '+6596845997'
#Starhub
#SMSC_NUM = '+6598540020'

from gsmmodem.modem import GsmModem

def loadDutyNumbers():
    global DUTYNUM, SUPERVISORNUM, STAFFNUM
    try:
      f = open('dutynumber.txt', 'r')
      DUTYNUM = f.readline().rstrip()
      f.close
    except IOError:
    	print('Duty number is empty. Ignoring...')
    try:
      with open('staffnumber.txt') as f:
        for line in f:
          if line:            # lines (ie skip them)
            if line.split()[1] == 'S':
              SUPERVISORNUM.append(line.split()[0])
              print(u'Loaded supervisor number: {0}'.format(line.split()[0]))
            elif line.split()[1] == 'D':
              STAFFNUM.append(line.split()[0])
              print(u'Loaded staff number: {0}'.format(line.split()[0]))
            else:
              print(u'Invalid entry in staff list: {0}'.format(line))
    except IOError:
    	print('Staff number list is empty. Please create staffnumber.txt yourself')

def loadSupervisorKeywords(supnumber):
    kw = []
    print(u'Loading keywords for: {0}'.format(supnumber))
    try:
      with open(u'{0}.txt'.format(supnumber)) as f:
        for line in f:
          if line:
            kw.append(line.lower().strip())
    except IOError:
      print('Supervisor keyword file does not exist - no keywords.')
    print('Done loading keywords')
    return kw

def saveSupervisorKeywords(supnumber, kw):
    print(u'Loading keywords for: {0}'.format(supnumber))
    with open(u'{0}.txt'.format(supnumber), 'w+') as f:
      for item in kw:
        f.write("%s\n" % item.lower())
        print(item)
    print('Done saving keywords for %s' % supnumber)
    return True

def saveLastIncomingNumber(number):
	print('Saving incoming number for quick reply')
	f=open('lastnumber.txt', 'w')
	f.write(number)
	f.close()
	return True

def getLastIncomingNumber():
	print('Retrieving last incoming number for quick reply')
	f=open('lastnumber.txt')
	number = f.read()
	f.close()
	return number

def processJobFile(filename):
	global POLLPATH, DESTPATH, modem
	lineno=1
	destno = ''
	msg = ''
	with open('%s%s' % (POLLPATH,filename)) as f:
		for line in f:
			if line:
				print(line.rstrip())
				if lineno==1:
					destno = line.rstrip()
					lineno += 1
				else:
					msg = '%s\n%s' % (msg,line)
	print('Sending to %s -> %s' % (destno, msg.strip()))
	modem.sendSms(destno, msg.strip())
	print('Moving %s to %s' % ('%s%s' % (POLLPATH, filename), '%s%s'% (DESTPATH, filename)))
	os.rename('%s%s' % (POLLPATH, filename), '%s%s' % (DESTPATH, filename))

def generateWordList(kw):
    wordlist = ""
    for item in kw:
      wordlist = wordlist + ',' + item
    #Return text without first comma
    return wordlist[1:]

def changeDutyNumber(sms):
    global DUTYNUM, SILENTNUM, modem
    oldDutyNum = DUTYNUM
    DUTYNUM = sms.number
    f = open('dutynumber.txt', 'w')
    f.write(DUTYNUM)
    f.close
    modem.sendSms(DUTYNUM, u'Thank you, your number {0} has been registered as the duty phone. Good luck!'.format(DUTYNUM))
    time.sleep(1)
    modem.setForwarding(0, 3, DUTYNUM)
    time.sleep(2)
    response = modem.setForwarding(0, 1, DUTYNUM)
    time.sleep(2)
    print(u'Duty number is now {0} - {1}'.format(DUTYNUM, response))
    modem.sendSms(oldDutyNum, u'Woohoo! {0} has just taken over the duty from you. You will no longer receive alerts or calls.'.format(DUTYNUM))
    print(u'Old duty number sent relief message {0}'.format(oldDutyNum))

def handleSms(sms):
    global STAFFNUM, SUPERVISORNUM, DUTYNUM, SILENTNUM
    print(u'== SMS message received ==\nFrom: {0}\nTime: {1}\nMessage:\n{2}\n'.format(sms.number, sms.time, sms.text))
    f = open('./messages.txt', 'a+')
    f.write(u'== SMS message received ==\nFrom: {0}\nTime: {1}\nMessage:\n{2}\n============\n\n'.format(sms.number, sms.time, sms.text))
    f.close
    if sms.number in STAFFNUM or sms.number in SUPERVISORNUM:
      keyword = sms.text.lower().split()[0]
      #============ TAKEOVER DUTY ===============
      if keyword == 'takeover':
        changeDutyNumber(sms)
      #============ GET HELP  ===============
      elif keyword == 'help':
        sms.reply('takeover=Start duty\nreply <msg>=Reply msg to last sender\nmsg <num> <msg>=Send msg to num\nstatus=Check status\nsilence <n>=No alert for n hours\nsub <kw>=Get alerts matching kw\nunsub <kw>=Unsub kw\nmykw=List kw')
      #============ REPLY LAST MSG ===============
      elif keyword == 'reply':
        dmsg = sms.text.split(' ', 1)[1]
        print('Replying message to %s.' % (dnum))
        sms.sendSms(getLastIncomingNumber(), dmsg)
        time.sleep(3)
        sms.reply('Your message to %s has been sent.' % (getLastIncomingNumber()))
      #============ FORWARDING MSG ===============
      elif keyword == 'msg':
        dnum = sms.text.split()[1]
        dmsg = sms.text.split(' ', 2)[2]
        if (dnum[:3] != '+65'):
          sms.reply('Your destination number must begin with +65. Message not sent, pls try again.')
        elif (len(dnum) != 11):
          sms.reply('Your destination number is not valid. Message not sent, pls try again.')
        else:
          print('Forwarding message to %s.' % (dnum))
          sms.sendSms(dnum, dmsg)
          time.sleep(3)
          sms.reply('Your message to %s has been sent.' % (dnum))
      #============ SILENCE n HOURS ===============
      elif keyword == 'silence' or keyword == 'silent':
        if sms.number == DUTYNUM:
          sms.reply('You are the duty phone and alerts cannot be silenced. :p')
        elif sms.number in SILENTNUM:
          sms.reply('You have already disabled any incoming alerts.')      
        else:
          SILENTNUM.append(sms.number)
          sms.reply('You will NOT be notified of incoming alerts. Reply "alert" to re-enable alerts.')
      #============ RE-ENABLE ALERTS ===============
      elif keyword == 'alert':
        if sms.number in SILENTNUM:
          SILENTNUM.remove(sms.number)
          sms.reply('You will be notified of incoming alerts.')
        else:
          sms.reply('You are already being notified of incoming alerts.')      
      #============ CHECK STATUS ===============
      elif keyword == 'status':
        v1='Supervisor' if sms.number in SUPERVISORNUM else 'Engineer'
        v2='No' if sms.number in SILENTNUM else 'Yes'
        kw = loadSupervisorKeywords(sms.number)
        v3=generateWordList(kw)
        sms.reply(u'Role: {0}\nAlerts: {1}\nOn-duty: {3}\nKeywords: {2}'.format(v1,v2,v3,DUTYNUM))      
      #============ SUBSCRIBE KW ===============
      elif keyword == 'sub':
        stafflevel='Supervisor' if sms.number in SUPERVISORNUM else 'Engineer'
        if stafflevel=='Engineer':
          sms.reply('Sorry - feature not available to you')
        else:
          kw = loadSupervisorKeywords(sms.number)
          newkw = sms.text.lower().split()[1]
          kw.append(newkw)
          saveSupervisorKeywords(sms.number, kw)
          sms.reply(u'Added keyword: {0}\nSub:{1}'.format(newkw,generateWordList(kw)))
      #============ GET LIST OF KW ===============
      elif keyword == 'mykw':
        stafflevel='Supervisor' if sms.number in SUPERVISORNUM else 'Engineer'
        if stafflevel=='Engineer':
          sms.reply('Sorry - feature not available to you')
        else:
          kw = loadSupervisorKeywords(sms.number)
          sms.reply(u'Your keywords:\n{0}'.format(generateWordList(kw)))
      #============ UNSUB KW ===============
      elif keyword == 'unsub':
        stafflevel='Supervisor' if sms.number in SUPERVISORNUM else 'Engineer'
        if stafflevel=='Engineer':
          sms.reply('Sorry - feature not available to you')
        else:
          kw = loadSupervisorKeywords(sms.number)
          delkw = sms.text.lower().split()[1]
          if delkw in kw:
            kw.remove(delkw)
            saveSupervisorKeywords(sms.number, kw)
            sms.reply(u'Removed: {0}\nSub:{1}'.format(delkw,generateWordList(kw)))
          else:
            sms.reply(u'You are not subscribed to {0}\nSub:{1}'.format(delkw,generateWordList(kw)))
      #============ INVALID COMMAND ===============
      else:
        sms.reply('Sorry I do not understand your message. Try "help" for assistance.')
    else: #NOT FROM STAFF, forward it!
      #NOTE: Need to add in timestamp and originating number. Need to cater for long SMS by breaking it into two.
      print(u'Sending SMS to duty number: {0} - {1}'.format(DUTYNUM, sms.text))
      sms.sendSms(DUTYNUM, u'[From: {0}]\n{1}'.format(sms.number,sms.text))
      #ONLY supervisors have keyword feature
      for supervisor in SUPERVISORNUM:
        if supervisor in SILENTNUM:
          print(u'Supervisor {0} is on silent mode.'.format(supervisor))
        elif supervisor == DUTYNUM:
          print(u'Supervisor {0} is on duty and already sent the message.'.format(supervisor))
        else: #OK, passed all the checks. Now check the supervisor filter.
          kw = loadSupervisorKeywords(supervisor)
          if '*all' in kw:
            print(u'Matched *ALL - Copying to supervisor {0}'.format(supervisor))
            sms.sendSms(supervisor, u'[From: {0}]\n{1}'.format(sms.number,sms.text))
          else:
            print('Checking keyword match')
            match = 0
            smslower = sms.text.lower()
            for line in  kw:
              line = line.lower()
              print(u'Match {0}?'.format(line))
              if line in smslower and match == 0:
                sms.sendSms(supervisor, u'[From: {0}]\n{1}'.format(sms.number,sms.text))
                print(u'Matched '.format(line))
                match = 1
            if match == 0:
              print(u'No match. Ignoring alert for {0}'.format(supervisor))
    print('Completed processing of incoming SMS...')
    
def main():
    global modem
    print('Initializing modem...')
    # Uncomment the following line to see what the modem is doing:
    #logging.basicConfig(format='%(levelname)s: %(message)s', level=logging.DEBUG)
    #logging.basicConfig(format='%(levelname)s: %(message)s', level=logging.INFO)
    modem = GsmModem(PORT, BAUDRATE, smsReceivedCallbackFunc=handleSms)
    modem.smsTextMode = False 
    modem.connect(PIN)
    modem.smsc = SMSC_NUM
    modem.checkForwarding(0)
    loadDutyNumbers()
    print(u'Current duty number is: {0}'.format(DUTYNUM))
    
    #CHECK SMS LIST
    messageList = modem.listStoredSms(STATUS_ALL, 'MT', True)
    messageList.extend(modem.listStoredSms(STATUS_ALL, 'SM', True))
    messageList.extend(modem.listStoredSms(STATUS_ALL, 'SR', True))
    messageList.extend(modem.listStoredSms(STATUS_ALL, None, True))
    for rSms in messageList:
      print (u'{0} - {1} :: {2}'.format(rSms.time, rSms.number,  rSms.text))
      handleSms(rSms)
      try:
        f = open('./messages.txt', 'a')
        f.write(u'== SMS message received (offline) ==\nFrom: {0}\nTime: {1}\nMessage:\n{2}\n============\n\n'.format(rSms.number, rSms.time, rSms$
        print(u'== SMS message received (offline) ==\nFrom: {0}\nTime: {1}\nMessage:\n{2}\n============\n\n'.format(rSms.number, rSms.time, rSms.t$
        f.close
      except Exception as e:
        print('Error saving message to disk. Probably encoding error or disk full')

    print('Waiting for SMS message...')    
    print(u'Signal strength is {0}% on {1} ({2}). IMEI {3}'.format(modem.signalStrength, modem.networkName, modem.imsi, modem.imei))
    try:
	while 1:
		qMsgs = os.listdir(POLLPATH)
		for qFile in qMsgs:
			print('Found job file: %s' % qFile)
			processJobFile(qFile)
	        modem.rxThread.join(5) # Specify a (huge) timeout so that it essentially blocks indefinitely, but still receives CTRL+C interrupt signal
    finally:
        modem.close();

if __name__ == '__main__':
    main()